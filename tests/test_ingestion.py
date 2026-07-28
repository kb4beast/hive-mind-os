from __future__ import annotations

import json
import tempfile
import unittest
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

from hive_mind_os.cli import build_defer_parser, build_ingest_parser
from hive_mind_os.courtroom import (
    BurdenOfProof,
    CapabilityMaturity,
    CaseParticipants,
    Disposition,
    DocketDecision,
    IdeaClaim,
    ImplementationState,
    SourceRecord,
    SourceStatus,
)
from hive_mind_os.ingestion import (
    ExhibitStore,
    SourceExhibit,
    adjudicate_with_exhibit,
    defer_obligation,
    reconcile_docket,
    register_exhibit,
)
from hive_mind_os.ledger import EvidenceLedger
from hive_mind_os.source_docket import FoundingSourceDocket

CAPTURED_AT = "2026-07-27T12:00:00+00:00"
PARTICIPANTS = CaseParticipants(
    "ingestion-advocate",
    "ingestion-cross-examiner",
    ("ingestion-judge",),
)


def _raises(
    exception: type[BaseException],
    match: str | None = None,
) -> AbstractContextManager[Any]:
    case = unittest.TestCase()
    if match is None:
        return case.assertRaises(exception)
    return case.assertRaisesRegex(exception, match)


def _source() -> SourceRecord:
    return SourceRecord(
        id="SRC-900",
        title="Test source",
        uri="https://example.invalid/source#fragment",
        kind="document",
        status=SourceStatus.PENDING_INGESTION,
        version_ref="document-v1",
        license_spdx=None,
        provenance_complete=False,
        object_type="content_snapshot",
    )


def _claim() -> IdeaClaim:
    return IdeaClaim(
        id="CLM-900",
        case_id="CASE-900",
        proposition="The supplied document contains one captured proposition",
        source_ids=("SRC-900",),
        category="capture",
        burden=BurdenOfProof.CAPTURE,
        implementation_state=ImplementationState.INVENTORIED,
        capability_maturity=CapabilityMaturity.SPECIFIED,
    )


def _decision() -> DocketDecision:
    return DocketDecision(
        claim_id="CLM-900",
        disposition=Disposition.DEFER,
        rationale="Defer until captured evidence is admitted.",
        advocate_case="The source may contain relevant evidence.",
        cross_examination="Do not infer unavailable content.",
        expert_findings=("Capture expert: require exact bytes.",),
    )


def _docket(source: SourceRecord | None = None) -> FoundingSourceDocket:
    return FoundingSourceDocket(
        schema_version=1,
        sources=(source or _source(),),
        claims=(_claim(),),
        decisions=(_decision(),),
    )


def _register(
    store: ExhibitStore,
    *,
    content: bytes = b"primary exhibit",
    license: str = "MIT",
    supply_method: str = "human-provided-file",
    parent_exhibit_digest: str | None = None,
) -> SourceExhibit:
    return register_exhibit(
        store,
        "SRC-900",
        content,
        original_filename="source.txt",
        media_type="text/plain",
        capturer_id="human-custodian",
        supply_method=supply_method,
        locator="https://example.invalid/source#page=1",
        license=license,
        captured_at=CAPTURED_AT,
        parent_exhibit_digest=parent_exhibit_digest,
    )


def _adjudicate(
    store: ExhibitStore,
    exhibit: SourceExhibit,
    *,
    source: SourceRecord | None = None,
) -> None:
    adjudicate_with_exhibit(
        store,
        source or _source(),
        _claim(),
        exhibit,
        participants=PARTICIPANTS,
        source_updates={
            "status": SourceStatus.VERIFIED,
            "provenance_complete": True,
            "unverified_digest_label": None,
        },
    )


def _case_exhibit_registration_is_content_addressed_and_tamper_fails_closed(
    tmp_path: Path,
) -> None:
    store = ExhibitStore(tmp_path / "evidence" / "sources")
    exhibit = _register(store)
    blob = (
        store.root
        / exhibit.source_id
        / "exhibits"
        / exhibit.content_digest.removeprefix("sha256:")
    )
    assert blob.read_bytes() == b"primary exhibit"
    assert exhibit.byte_count == len(b"primary exhibit")

    blob.write_bytes(b"tampered")
    with _raises(ValueError, match="stored exhibit digest mismatch"):
        store.read(exhibit.source_id, exhibit.content_digest)


def _case_derived_artifact_requires_an_existing_parent(tmp_path: Path) -> None:
    store = ExhibitStore(tmp_path / "sources")
    with _raises(ValueError, match="require a parent"):
        _register(store, supply_method="agent-derived")

    missing_digest = "sha256:" + "1" * 64
    with _raises(FileNotFoundError):
        _register(
            store,
            supply_method="agent-derived",
            parent_exhibit_digest=missing_digest,
        )

    parent = _register(store)
    derived = _register(
        store,
        content=b"derived text",
        supply_method="agent-derived",
        parent_exhibit_digest=parent.content_digest,
    )
    assert derived.parent_exhibit_digest == parent.content_digest


def _case_unblocking_requires_both_exhibit_and_promoting_verdict(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    store = ExhibitStore(repository / "evidence" / "sources")
    exhibit = _register(store)
    original = _docket()
    assert original.audit().machine_blocked_claim_ids == ("CLM-900",)

    exhibit_only = reconcile_docket(original, repository)
    assert exhibit_only.audit().machine_blocked_claim_ids == ("CLM-900",)

    absent = SourceExhibit(
        schema_version=1,
        source_id="SRC-900",
        content_digest="sha256:" + "2" * 64,
        original_filename="absent.txt",
        media_type="text/plain",
        byte_count=1,
        captured_at=CAPTURED_AT,
        capturer_id="human-custodian",
        supply_method="human-provided-file",
        locator="https://example.invalid/absent",
        license="MIT",
    )
    with _raises(FileNotFoundError):
        _adjudicate(store, absent)

    _adjudicate(store, exhibit)
    reconciled = reconcile_docket(original, repository)
    assert reconciled.audit().machine_blocked_claim_ids == ()
    assert reconciled.sources[0].content_digest == exhibit.content_digest


def _case_adjudication_driver_enforces_court_identity_separation() -> None:
    with _raises(ValueError, match="independent identities"):
        CaseParticipants("same", "cross", ("same",))


def _case_defer_obligation_records_review_date_and_keeps_claim_blocked(
    tmp_path: Path,
) -> None:
    store = ExhibitStore(tmp_path / "evidence" / "sources")
    deferred = defer_obligation(
        store,
        "B-SRC-TEST",
        (_source(),),
        reason="The custodian has not supplied the original bytes.",
        review_by="2027-01-31",
        participants=PARTICIPANTS,
    )
    record = json.loads(deferred.record_path.read_text(encoding="utf-8"))
    assert record["review_by"] == "2027-01-31"
    assert record["verdict"]["disposition"] == "defer"
    assert _docket().audit().machine_blocked_claim_ids == ("CLM-900",)


def _case_license_unknown_blocks_and_resolved_spdx_with_exhibit_lifts_blocker(
    tmp_path: Path,
) -> None:
    unknown_repository = tmp_path / "unknown"
    unknown_store = ExhibitStore(unknown_repository / "evidence" / "sources")
    unknown = _register(unknown_store, license="unknown")
    _adjudicate(unknown_store, unknown)
    unknown_docket = reconcile_docket(_docket(), unknown_repository)
    assert unknown_docket.sources[0].license_spdx is None
    assert unknown_docket.audit().machine_blocked_claim_ids == ("CLM-900",)

    resolved_repository = tmp_path / "resolved"
    resolved_store = ExhibitStore(resolved_repository / "evidence" / "sources")
    resolved = _register(resolved_store, license="Apache-2.0")
    _adjudicate(resolved_store, resolved)
    resolved_docket = reconcile_docket(_docket(), resolved_repository)
    assert resolved_docket.sources[0].license_spdx == "Apache-2.0"
    assert resolved_docket.audit().machine_blocked_claim_ids == ()


def _case_adjudication_rejects_metadata_not_bound_to_registered_bytes(
    tmp_path: Path,
) -> None:
    store = ExhibitStore(tmp_path / "evidence" / "sources")
    registered = _register(store, license="unknown")
    forged_license = SourceExhibit(
        **{**registered.to_record(), "license": "MIT"},
    )
    with _raises(ValueError, match="metadata was not registered"):
        _adjudicate(store, forged_license)


def _case_operations_are_additive_to_docket_counts(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    store = ExhibitStore(repository / "evidence" / "sources")
    baseline = _docket()
    observations = [(baseline.source_count, baseline.claim_count)]
    exhibit = _register(store)
    observations.append(
        (
            reconcile_docket(baseline, repository).source_count,
            reconcile_docket(baseline, repository).claim_count,
        )
    )
    _adjudicate(store, exhibit)
    reconciled = reconcile_docket(baseline, repository)
    observations.append((reconciled.source_count, reconciled.claim_count))
    defer_obligation(
        store,
        "B-SRC-LATER",
        (reconciled.sources[0],),
        reason="Independent license review remains scheduled.",
        review_by="2027-02-28",
        participants=PARTICIPANTS,
    )
    observations.append((reconciled.source_count, reconciled.claim_count))
    assert all(
        after[0] >= before[0] and after[1] >= before[1]
        for before, after in zip(observations, observations[1:])
    )


def _case_fabricated_digest_is_rejected_and_ledgered(tmp_path: Path) -> None:
    ledger = EvidenceLedger()
    store = ExhibitStore(tmp_path / "sources", ledger=ledger)
    with _raises(ValueError, match="claimed digest"):
        register_exhibit(
            store,
            "SRC-900",
            b"actual bytes",
            original_filename="source.txt",
            media_type="text/plain",
            capturer_id="human-custodian",
            supply_method="human-provided-file",
            locator="https://example.invalid/source",
            license="unknown",
            captured_at=CAPTURED_AT,
            expected_digest="sha256:" + "0" * 64,
        )
    events = ledger.events("source-ingestion")
    assert [event["event_type"] for event in events] == ["source.exhibit.rejected"]
    assert events[0]["payload"]["reason"] == "digest mismatch"


def _case_cli_parsers_cover_ingest_and_defer_contracts() -> None:
    ingest = build_ingest_parser().parse_args(
        [
            "--source",
            "SRC-005",
            "--file",
            "transcript.txt",
            "--locator",
            "https://example.invalid/video#t=10",
            "--media-type",
            "text/plain",
            "--license",
            "unknown",
        ]
    )
    assert ingest.supply_method == "human-provided-file"
    deferred = build_defer_parser().parse_args(
        [
            "--source",
            "SRC-005",
            "--reason",
            "Transcript unavailable",
            "--review-by",
            "2027-01-31",
        ]
    )
    assert deferred.source == ["SRC-005"]


class IngestionTests(unittest.TestCase):
    def _run_with_temporary_path(
        self,
        test_case: Callable[[Path], None],
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            test_case(Path(temporary_directory))

    def test_exhibit_registration_is_content_addressed_and_tamper_fails_closed(
        self,
    ) -> None:
        self._run_with_temporary_path(
            _case_exhibit_registration_is_content_addressed_and_tamper_fails_closed
        )

    def test_derived_artifact_requires_an_existing_parent(self) -> None:
        self._run_with_temporary_path(
            _case_derived_artifact_requires_an_existing_parent
        )

    def test_unblocking_requires_both_exhibit_and_promoting_verdict(self) -> None:
        self._run_with_temporary_path(
            _case_unblocking_requires_both_exhibit_and_promoting_verdict
        )

    def test_adjudication_driver_enforces_court_identity_separation(self) -> None:
        _case_adjudication_driver_enforces_court_identity_separation()

    def test_defer_obligation_records_review_date_and_keeps_claim_blocked(
        self,
    ) -> None:
        self._run_with_temporary_path(
            _case_defer_obligation_records_review_date_and_keeps_claim_blocked
        )

    def test_license_unknown_blocks_and_resolved_spdx_with_exhibit_lifts_blocker(
        self,
    ) -> None:
        self._run_with_temporary_path(
            _case_license_unknown_blocks_and_resolved_spdx_with_exhibit_lifts_blocker
        )

    def test_adjudication_rejects_metadata_not_bound_to_registered_bytes(
        self,
    ) -> None:
        self._run_with_temporary_path(
            _case_adjudication_rejects_metadata_not_bound_to_registered_bytes
        )

    def test_operations_are_additive_to_docket_counts(self) -> None:
        self._run_with_temporary_path(_case_operations_are_additive_to_docket_counts)

    def test_fabricated_digest_is_rejected_and_ledgered(self) -> None:
        self._run_with_temporary_path(
            _case_fabricated_digest_is_rejected_and_ledgered
        )

    def test_cli_parsers_cover_ingest_and_defer_contracts(self) -> None:
        _case_cli_parsers_cover_ingest_and_defer_contracts()
