from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
from pathlib import Path, PurePath
from typing import TYPE_CHECKING, Any, Mapping

from .contracts import validate_contract
from .courtroom import (
    BurdenOfProof,
    CaseParticipants,
    CourtCase,
    Courtroom,
    CourtVerdict,
    Disposition,
    EvidenceStance,
    EvidenceStrength,
    Exhibit,
    IdeaClaim,
    ImplementationState,
    SourceRecord,
    SourceStatus,
)
from .models import utc_now

if TYPE_CHECKING:
    from .ledger import EvidenceLedger
    from .source_docket import FoundingSourceDocket


_SOURCE_ID = re.compile(r"SRC-[0-9]{3,}\Z")
_SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
_MEDIA_TYPE = re.compile(
    r"[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+(?:\s*;\s*[^,\r\n]+)?\Z"
)
_SPDX_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9-.+]*\Z")
_LICENSE_UNRESOLVED = frozenset({"unknown", "unresolved-pending-review"})
_SUPPLY_METHODS = frozenset({"human-provided-file", "agent-derived"})
_SOURCE_FIELDS = frozenset(SourceRecord.__dataclass_fields__)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _validate_rfc3339(value: str) -> None:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError("capture time must be RFC 3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("capture time must include an explicit offset")


def _validate_locator(value: str) -> None:
    if not value.strip() or any(character in value for character in "\r\n"):
        raise ValueError("exact locator must be a non-empty single line")
    if ":" not in value:
        raise ValueError("exact locator must include a URI scheme")


def _validate_license(value: str) -> None:
    if value in _LICENSE_UNRESOLVED:
        return
    if _SPDX_ID.fullmatch(value) is None:
        raise ValueError("license must be an SPDX id, unknown, or unresolved-pending-review")


def _safe_original_filename(value: str) -> str:
    if not value.strip() or "\x00" in value:
        raise ValueError("original filename is required")
    name = PurePath(value).name
    if name in {"", ".", ".."}:
        raise ValueError("original filename is invalid")
    return name


def _write_additive_json(path: Path, record: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _canonical_bytes(record) + b"\n"
    try:
        with path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
    except FileExistsError:
        if path.read_bytes() != payload:
            raise ValueError(f"append-only record collision: {path}") from None


@dataclass(frozen=True, slots=True)
class LicenseRecord:
    value: str
    exhibit_digest: str

    def __post_init__(self) -> None:
        _validate_license(self.value)
        if _SHA256.fullmatch(self.exhibit_digest) is None:
            raise ValueError("license record requires an exhibit SHA-256 digest")

    @property
    def resolved_spdx(self) -> str | None:
        return None if self.value in _LICENSE_UNRESOLVED else self.value


@dataclass(frozen=True, slots=True)
class SourceExhibit:
    schema_version: int
    source_id: str
    content_digest: str
    original_filename: str
    media_type: str
    byte_count: int
    captured_at: str
    capturer_id: str
    supply_method: str
    locator: str
    license: str
    parent_exhibit_digest: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported source exhibit schema")
        if _SOURCE_ID.fullmatch(self.source_id) is None:
            raise ValueError("invalid source id")
        if _SHA256.fullmatch(self.content_digest) is None:
            raise ValueError("invalid exhibit digest")
        _safe_original_filename(self.original_filename)
        if _MEDIA_TYPE.fullmatch(self.media_type) is None:
            raise ValueError("invalid media type")
        if type(self.byte_count) is not int or self.byte_count < 0:
            raise ValueError("byte count must be a non-negative integer")
        _validate_rfc3339(self.captured_at)
        if not self.capturer_id.strip():
            raise ValueError("capturer identity is required")
        if self.supply_method not in _SUPPLY_METHODS:
            raise ValueError("unsupported supply method")
        _validate_locator(self.locator)
        _validate_license(self.license)
        if self.supply_method == "agent-derived":
            if (
                self.parent_exhibit_digest is None
                or _SHA256.fullmatch(self.parent_exhibit_digest) is None
            ):
                raise ValueError("derived exhibits require a parent exhibit digest")
        elif self.parent_exhibit_digest is not None:
            raise ValueError("human-provided exhibits cannot claim a derived parent")

    def to_record(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AdjudicationRecord:
    source_id: str
    claim_id: str
    exhibit_digest: str
    previous_source_digest: str
    result_source: Mapping[str, object]
    participants: CaseParticipants
    verdict: CourtVerdict
    record_path: Path


@dataclass(frozen=True, slots=True)
class DeferredObligation:
    obligation_id: str
    source_ids: tuple[str, ...]
    reason: str
    review_by: str
    participants: CaseParticipants
    verdict: CourtVerdict
    recorded_at: str
    record_path: Path


class ExhibitStore:
    """Content-addressed, append-only source exhibit storage."""

    def __init__(
        self,
        root: str | Path,
        *,
        ledger: EvidenceLedger | None = None,
    ) -> None:
        self.root = Path(root)
        self.ledger = ledger

    def _event(
        self,
        event_type: str,
        actor: str,
        payload: dict[str, object],
    ) -> None:
        if self.ledger is not None:
            self.ledger.append_event("source-ingestion", event_type, actor, payload)

    def _source_root(self, source_id: str) -> Path:
        if _SOURCE_ID.fullmatch(source_id) is None:
            raise ValueError("invalid source id")
        root = self.root.resolve()
        candidate = (root / source_id).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            raise ValueError("source evidence path escapes the evidence root") from None
        return candidate

    @staticmethod
    def _record_digest(exhibit: SourceExhibit) -> str:
        return _digest(_canonical_bytes(exhibit.to_record()))

    def _record_path(self, exhibit: SourceExhibit) -> Path:
        return (
            self._source_root(exhibit.source_id)
            / "records"
            / f"{self._record_digest(exhibit).removeprefix('sha256:')}.json"
        )

    def _has_record_for_digest(self, source_id: str, content_digest: str) -> bool:
        directory = self._source_root(source_id) / "records"
        if not directory.is_dir():
            return False
        for path in directory.glob("*.json"):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                exhibit = SourceExhibit(**raw)
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
            if exhibit.source_id == source_id and exhibit.content_digest == content_digest:
                return True
        return False

    def register(
        self,
        source_id: str,
        content: bytes,
        *,
        original_filename: str,
        media_type: str,
        capturer_id: str,
        supply_method: str,
        locator: str,
        license: str,
        captured_at: str | None = None,
        parent_exhibit_digest: str | None = None,
        expected_digest: str | None = None,
    ) -> SourceExhibit:
        if not isinstance(content, bytes):
            raise TypeError("exhibit content must be bytes")
        actual_digest = _digest(content)
        if expected_digest is not None and expected_digest != actual_digest:
            self._event(
                "source.exhibit.rejected",
                capturer_id,
                {
                    "source_id": source_id,
                    "claimed_digest": expected_digest,
                    "actual_digest": actual_digest,
                    "reason": "digest mismatch",
                },
            )
            raise ValueError("claimed digest does not match supplied bytes")
        exhibit = SourceExhibit(
            schema_version=1,
            source_id=source_id,
            content_digest=actual_digest,
            original_filename=_safe_original_filename(original_filename),
            media_type=media_type,
            byte_count=len(content),
            captured_at=captured_at or utc_now(),
            capturer_id=capturer_id,
            supply_method=supply_method,
            locator=locator,
            license=license,
            parent_exhibit_digest=parent_exhibit_digest,
        )
        source_root = self._source_root(source_id)
        if exhibit.parent_exhibit_digest is not None:
            self.read(source_id, exhibit.parent_exhibit_digest)
            if not self._has_record_for_digest(source_id, exhibit.parent_exhibit_digest):
                raise ValueError("derived exhibit parent has no admitted metadata record")
        blob_path = source_root / "exhibits" / actual_digest.removeprefix("sha256:")
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with blob_path.open("xb") as handle:
                handle.write(content)
                handle.flush()
        except FileExistsError:
            if _digest(blob_path.read_bytes()) != actual_digest:
                self._event(
                    "source.exhibit.rejected",
                    capturer_id,
                    {
                        "source_id": source_id,
                        "claimed_digest": actual_digest,
                        "reason": "stored content digest mismatch",
                    },
                )
                raise ValueError("stored exhibit digest mismatch") from None
        record = exhibit.to_record()
        record_digest = self._record_digest(exhibit).removeprefix("sha256:")
        _write_additive_json(
            self._record_path(exhibit),
            record,
        )
        self._event(
            "source.exhibit.registered",
            capturer_id,
            {
                "source_id": source_id,
                "content_digest": actual_digest,
                "record_digest": f"sha256:{record_digest}",
            },
        )
        return exhibit

    def admit(self, exhibit: SourceExhibit) -> str:
        """Verify raw bytes and the exact immutable metadata record."""

        self.read(exhibit.source_id, exhibit.content_digest)
        path = self._record_path(exhibit)
        expected = _canonical_bytes(exhibit.to_record()) + b"\n"
        try:
            observed = path.read_bytes()
        except FileNotFoundError:
            raise ValueError("exhibit metadata was not registered") from None
        if observed != expected:
            raise ValueError("exhibit metadata record does not match admitted exhibit")
        return self._record_digest(exhibit)

    def read(self, source_id: str, content_digest: str) -> bytes:
        if _SHA256.fullmatch(content_digest) is None:
            raise ValueError("invalid exhibit digest")
        path = (
            self._source_root(source_id)
            / "exhibits"
            / content_digest.removeprefix("sha256:")
        )
        content = path.read_bytes()
        if _digest(content) != content_digest:
            self._event(
                "source.exhibit.rejected",
                "exhibit-store",
                {
                    "source_id": source_id,
                    "claimed_digest": content_digest,
                    "reason": "stored content digest mismatch",
                },
            )
            raise ValueError("stored exhibit digest mismatch")
        return content

    def reconciliation_path(self, source_id: str, record: Mapping[str, object]) -> Path:
        digest = _digest(_canonical_bytes(record)).removeprefix("sha256:")
        return self._source_root(source_id) / "reconciliations" / f"{digest}.json"

    def deferral_path(self, obligation_id: str, record: Mapping[str, object]) -> Path:
        if not obligation_id.strip() or any(character in obligation_id for character in "/\\"):
            raise ValueError("invalid obligation id")
        digest = _digest(_canonical_bytes(record)).removeprefix("sha256:")
        return self.root / "_obligations" / obligation_id / f"{digest}.json"


def register_exhibit(
    store: ExhibitStore,
    source_id: str,
    content: bytes,
    **metadata: Any,
) -> SourceExhibit:
    return store.register(source_id, content, **metadata)


def _source_contract_digest(source: SourceRecord) -> str:
    return _digest(_canonical_bytes(source.to_contract()))


def _optional_string(contract: Mapping[str, object], key: str) -> str | None:
    value = contract.get(key)
    return value if isinstance(value, str) else None


def _source_from_contract(contract: Mapping[str, object]) -> SourceRecord:
    validation = validate_contract("source", dict(contract))
    if not validation.valid:
        raise ValueError("reconciled source violates source contract: " + "; ".join(validation.issues))
    unknown = set(contract) - _SOURCE_FIELDS - {"schema_version"}
    if unknown:
        raise ValueError("reconciled source contains unsupported fields")
    return SourceRecord(
        id=str(contract["id"]),
        title=str(contract["title"]),
        uri=str(contract["uri"]),
        kind=str(contract["kind"]),
        status=SourceStatus(str(contract["status"])),
        version_ref=_optional_string(contract, "version_ref"),
        license_spdx=_optional_string(contract, "license_spdx"),
        content_digest=_optional_string(contract, "content_digest"),
        unverified_digest_label=_optional_string(
            contract,
            "unverified_digest_label",
        ),
        provenance_complete=bool(contract["provenance_complete"]),
        requires_complete_ingestion=bool(contract["requires_complete_ingestion"]),
        object_type=_optional_string(contract, "object_type"),
        retrieved_at=_optional_string(contract, "retrieved_at"),
        snapshot_ref=_optional_string(contract, "snapshot_ref"),
    )


def adjudicate_with_exhibit(
    store: ExhibitStore,
    source: SourceRecord,
    claim: IdeaClaim,
    exhibit: SourceExhibit,
    *,
    participants: CaseParticipants,
    source_updates: Mapping[str, object] | None = None,
) -> AdjudicationRecord:
    """Adjudicate one captured exhibit and append a source reconciliation on success."""

    exhibit_record_digest = store.admit(exhibit)
    if exhibit.source_id != source.id or source.id not in claim.source_ids:
        raise ValueError("exhibit, source, and claim are not bound")
    updates = dict(source_updates or {})
    forbidden = set(updates) - {
        "status",
        "version_ref",
        "license_spdx",
        "content_digest",
        "unverified_digest_label",
        "provenance_complete",
        "requires_complete_ingestion",
        "object_type",
        "retrieved_at",
        "snapshot_ref",
    }
    if forbidden:
        raise ValueError("source reconciliation attempts to mutate immutable identity fields")
    updates.setdefault("content_digest", exhibit.content_digest)
    updates.setdefault("retrieved_at", exhibit.captured_at)
    updates.setdefault(
        "snapshot_ref",
        (
            f"evidence/sources/{source.id}/exhibits/"
            f"{exhibit.content_digest.removeprefix('sha256:')}"
        ),
    )
    license_record = LicenseRecord(exhibit.license, exhibit.content_digest)
    if license_record.resolved_spdx is not None:
        updates.setdefault("license_spdx", license_record.resolved_spdx)
    candidate = replace(source, **updates)
    source_validation = validate_contract("source", candidate.to_contract())
    if not source_validation.valid:
        raise ValueError(
            "source reconciliation violates source contract: "
            + "; ".join(source_validation.issues)
        )
    courtroom_exhibit = Exhibit(
        id=f"EX-{exhibit.content_digest.removeprefix('sha256:')[:16]}",
        claim_id=claim.id,
        source_id=source.id,
        stance=EvidenceStance.SUPPORTS,
        strength=EvidenceStrength.DOCUMENTED,
        locator=exhibit.locator,
        content_digest=exhibit.content_digest,
    )
    verdict = Courtroom((candidate,)).hear(
        CourtCase(
            claim=claim,
            participants=participants,
            exhibits=(courtroom_exhibit,),
            testimony=(),
        )
    )
    if verdict.disposition not in {Disposition.ADOPT, Disposition.ADAPT}:
        raise ValueError("courtroom did not authorize source reconciliation")
    record: dict[str, object] = {
        "schema_version": 1,
        "source_id": source.id,
        "claim_id": claim.id,
        "exhibit_digest": exhibit.content_digest,
        "exhibit_record_digest": exhibit_record_digest,
        "previous_source_digest": _source_contract_digest(source),
        "result_source": candidate.to_contract(),
        "participants": {
            "advocate_id": participants.advocate_id,
            "cross_examiner_id": participants.cross_examiner_id,
            "judge_ids": list(participants.judge_ids),
        },
        "verdict": {
            "claim_id": verdict.claim_id,
            "disposition": verdict.disposition.value,
            "score": verdict.score,
            "reasons": list(verdict.reasons),
            "obligations": list(verdict.obligations),
            "decided_by": list(verdict.decided_by),
        },
        "recorded_at": utc_now(),
    }
    path = store.reconciliation_path(source.id, record)
    _write_additive_json(path, record)
    store._event(
        "source.reconciliation.recorded",
        ",".join(participants.judge_ids),
        {
            "source_id": source.id,
            "claim_id": claim.id,
            "exhibit_digest": exhibit.content_digest,
            "record": path.as_posix(),
        },
    )
    return AdjudicationRecord(
        source.id,
        claim.id,
        exhibit.content_digest,
        str(record["previous_source_digest"]),
        candidate.to_contract(),
        participants,
        verdict,
        path,
    )


def defer_obligation(
    store: ExhibitStore,
    obligation_id: str,
    sources: tuple[SourceRecord, ...],
    *,
    reason: str,
    review_by: str,
    participants: CaseParticipants,
) -> DeferredObligation:
    if not sources:
        raise ValueError("deferred obligation requires at least one source")
    if not reason.strip():
        raise ValueError("defer reason is required")
    try:
        review_date = date.fromisoformat(review_by)
    except ValueError as error:
        raise ValueError("review-by must be an ISO calendar date") from error
    today = datetime.now().astimezone().date()
    if review_date <= today:
        raise ValueError("review-by must be a future date")
    source_ids = tuple(source.id for source in sources)
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("deferred obligation contains duplicate sources")
    claim = IdeaClaim(
        id=obligation_id,
        case_id=f"CASE-{obligation_id}",
        proposition=reason,
        source_ids=source_ids,
        category="source_evidence_obligation",
        burden=BurdenOfProof.CAPTURE,
        implementation_state=ImplementationState.INVENTORIED,
    )
    verdict = Courtroom(sources).hear(
        CourtCase(
            claim=claim,
            participants=participants,
            exhibits=(),
            testimony=(),
            unresolved_objections=(reason,),
        )
    )
    if verdict.disposition is not Disposition.DEFER:
        raise ValueError("uncaptured obligation must receive a defer verdict")
    recorded_at = utc_now()
    record: dict[str, object] = {
        "schema_version": 1,
        "obligation_id": obligation_id,
        "source_ids": list(source_ids),
        "reason": reason,
        "review_by": review_by,
        "recorded_at": recorded_at,
        "participants": {
            "advocate_id": participants.advocate_id,
            "cross_examiner_id": participants.cross_examiner_id,
            "judge_ids": list(participants.judge_ids),
        },
        "verdict": {
            "claim_id": verdict.claim_id,
            "disposition": verdict.disposition.value,
            "score": verdict.score,
            "reasons": list(verdict.reasons),
            "obligations": list(verdict.obligations),
            "decided_by": list(verdict.decided_by),
        },
    }
    path = store.deferral_path(obligation_id, record)
    _write_additive_json(path, record)
    store._event(
        "source.obligation.deferred",
        ",".join(participants.judge_ids),
        {
            "obligation_id": obligation_id,
            "source_ids": list(source_ids),
            "review_by": review_by,
            "record": path.as_posix(),
        },
    )
    return DeferredObligation(
        obligation_id,
        source_ids,
        reason,
        review_by,
        participants,
        verdict,
        recorded_at,
        path,
    )


def _parse_participants(record: Mapping[str, object]) -> CaseParticipants:
    raw = record.get("participants")
    if not isinstance(raw, Mapping):
        raise ValueError("reconciliation participants are missing")
    judges = raw.get("judge_ids")
    if not isinstance(judges, list) or any(not isinstance(item, str) for item in judges):
        raise ValueError("reconciliation judges are invalid")
    advocate = raw.get("advocate_id")
    cross = raw.get("cross_examiner_id")
    if not isinstance(advocate, str) or not isinstance(cross, str):
        raise ValueError("reconciliation court identities are invalid")
    return CaseParticipants(advocate, cross, tuple(judges))


def _load_reconciliation(
    path: Path,
    store: ExhibitStore,
    source: SourceRecord,
    claims: Mapping[str, IdeaClaim],
) -> SourceRecord:
    payload = path.read_bytes()
    expected_name = _digest(payload.rstrip(b"\n")).removeprefix("sha256:") + ".json"
    if path.name != expected_name:
        raise ValueError(f"reconciliation filename digest mismatch: {path}")
    record = json.loads(payload)
    if not isinstance(record, Mapping) or record.get("schema_version") != 1:
        raise ValueError("unsupported reconciliation record")
    if record.get("source_id") != source.id:
        raise ValueError("reconciliation source identity mismatch")
    if record.get("previous_source_digest") != _source_contract_digest(source):
        raise ValueError("reconciliation does not extend the current source state")
    claim_id = record.get("claim_id")
    claim = claims.get(claim_id) if isinstance(claim_id, str) else None
    if claim is None or source.id not in claim.source_ids:
        raise ValueError("reconciliation references an unknown or unrelated claim")
    digest = record.get("exhibit_digest")
    if not isinstance(digest, str):
        raise ValueError("reconciliation exhibit digest is missing")
    record_digest = record.get("exhibit_record_digest")
    if not isinstance(record_digest, str) or _SHA256.fullmatch(record_digest) is None:
        raise ValueError("reconciliation exhibit metadata digest is missing")
    store.read(source.id, digest)
    record_path = (
        store._source_root(source.id)
        / "records"
        / f"{record_digest.removeprefix('sha256:')}.json"
    )
    try:
        exhibit_record = json.loads(record_path.read_text(encoding="utf-8"))
        admitted_exhibit = SourceExhibit(**exhibit_record)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("reconciliation exhibit metadata is invalid") from error
    if (
        admitted_exhibit.source_id != source.id
        or admitted_exhibit.content_digest != digest
        or store._record_digest(admitted_exhibit) != record_digest
    ):
        raise ValueError("reconciliation exhibit metadata is not bound to the exhibit")
    participants = _parse_participants(record)
    verdict = record.get("verdict")
    if not isinstance(verdict, Mapping):
        raise ValueError("reconciliation verdict is missing")
    if verdict.get("claim_id") != claim.id:
        raise ValueError("reconciliation verdict claim mismatch")
    if verdict.get("disposition") not in {
        Disposition.ADOPT.value,
        Disposition.ADAPT.value,
    }:
        raise ValueError("reconciliation lacks a promoting courtroom verdict")
    if verdict.get("decided_by") != list(participants.judge_ids):
        raise ValueError("reconciliation verdict judge mismatch")
    result = record.get("result_source")
    if not isinstance(result, Mapping):
        raise ValueError("reconciliation result source is missing")
    candidate = _source_from_contract(result)
    if (
        candidate.id != source.id
        or candidate.title != source.title
        or candidate.uri != source.uri
        or candidate.kind != source.kind
    ):
        raise ValueError("reconciliation mutated immutable source identity")
    if candidate.content_digest != digest:
        raise ValueError("reconciliation source digest is not bound to the exhibit")
    return candidate


def reconcile_docket(
    docket: FoundingSourceDocket,
    repository: str | Path,
) -> FoundingSourceDocket:
    """Apply a unique append-only chain of admitted reconciliation records."""

    repository_path = Path(repository).resolve()
    store = ExhibitStore(repository_path / "evidence" / "sources")
    claims = {claim.id: claim for claim in docket.claims}
    reconciled: list[SourceRecord] = []
    for initial in docket.sources:
        source = initial
        directory = store._source_root(source.id) / "reconciliations"
        pending = list(directory.glob("*.json")) if directory.is_dir() else []
        while pending:
            matching: list[Path] = []
            for path in pending:
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError) as error:
                    raise ValueError(f"cannot read reconciliation {path}: {error}") from error
                if (
                    isinstance(raw, Mapping)
                    and raw.get("previous_source_digest") == _source_contract_digest(source)
                ):
                    matching.append(path)
            if not matching:
                raise ValueError(f"orphaned reconciliation records for {source.id}")
            if len(matching) != 1:
                raise ValueError(f"branched reconciliation history for {source.id}")
            selected = matching[0]
            source = _load_reconciliation(selected, store, source, claims)
            pending.remove(selected)
        reconciled.append(source)
    return type(docket)(
        schema_version=docket.schema_version,
        sources=tuple(reconciled),
        claims=docket.claims,
        decisions=docket.decisions,
    )
