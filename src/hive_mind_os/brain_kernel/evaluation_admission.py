"""Read-only verification of declared evaluation subjects and retained metrics.

This module neither authenticates actors nor grants promotion authority. Prompt
artifact digests are declarations: a registry must separately resolve its bytes,
check the live parent, and consume evidence at its own commit boundary.
"""

from __future__ import annotations

import json
import math
import os
import stat
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

from .canonical import canonical_bytes, canonical_digest
from .evaluation_runtime import (
    ChallengerDescriptor,
    EvaluationContract,
    EvaluationError,
    EvaluationIdentities,
    EvaluationRecordReference,
    EvaluationVerdict,
    GuardrailSpec,
    PromptEvaluationSubject,
    SurfaceKind,
    SurfaceResult,
    _exact_document,
    _require_digest,
    _require_identifier,
    _score_evaluation,
)

__all__ = [
    "EvaluationAdmissionError", "ParsedEvaluationRecord", "ResolvedKeepEvidence",
    "load_evaluation_record", "resolve_keep_evidence", "resolve_decision_evidence", "recheck_resolved_evidence",
]


class EvaluationAdmissionError(RuntimeError):
    """An attributed diagnostic, not an authenticated or durable rejection."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _fail(code: str, message: str) -> None:
    raise EvaluationAdmissionError(code, message)


@dataclass(frozen=True, slots=True)
class ParsedHoldout:
    holdout_id: str
    evaluator_id: str | None
    prediction_digest: str | None
    seal_sequence: int | None
    reveal_sequence: int | None
    valid: bool
    violations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ParsedEvaluationRecord:
    schema_version: int
    evaluation_id: str
    record_digest: str
    raw_bytes: bytes
    canonical_document_bytes: bytes
    descriptor: ChallengerDescriptor
    identities: EvaluationIdentities
    contract_fingerprint: str
    verdict: EvaluationVerdict
    reasons: tuple[str, ...]
    primary_effect: float | None
    required_effect: float | None
    noise_floor: float | None
    holdout: ParsedHoldout
    surfaces: tuple[SurfaceResult, ...]
    selection_policy: str | None
    requested_primary_held_out_name: str | None
    resolved_primary_held_out_name: str | None
    primary_scored: bool | None
    promotion_subject: PromptEvaluationSubject | None
    promotion_subject_digest: str | None

    def document(self) -> dict[str, Any]:
        """Return a detached historical document; trusted state stays immutable."""
        return json.loads(self.canonical_document_bytes)


@dataclass(frozen=True, slots=True)
class FileSnapshot:
    path: str
    resource: str
    raw_bytes: bytes
    raw_digest: str


@dataclass(frozen=True, slots=True)
class ResolvedKeepEvidence:
    subject: PromptEvaluationSubject
    reference: EvaluationRecordReference
    record: ParsedEvaluationRecord
    contract: EvaluationContract
    snapshots: tuple[FileSnapshot, ...]


_BASE_FIELDS = {
    "schema_version", "descriptor", "identities", "contract_fingerprint",
    "verdict", "reasons", "primary_effect", "required_effect", "noise_floor",
    "holdout", "surfaces", "evaluation_id",
}
_SELECTION_FIELDS = {
    "selection_policy", "requested_primary_held_out_name",
    "resolved_primary_held_out_name", "primary_scored",
}


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError("duplicate JSON key: " + key)
        document[key] = value
    return document


def _reject_constant(value: str) -> None:
    raise ValueError("non-finite JSON number: " + value)


def _json_document(raw: bytes, resource: str) -> dict[str, Any]:
    try:
        document = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
        if type(document) is not dict:
            raise ValueError("document must be an object")
        if raw != canonical_bytes(document) + b"\n":
            raise ValueError("document is not canonical JSON followed by one LF")
        return document
    except (ValueError, TypeError, OverflowError, RecursionError) as error:
        raise EvaluationAdmissionError(resource + "-malformed", str(error)) from error


def _local_path(value: str) -> Path:
    if (type(value) is not str or not value or "\0" in value or "://" in value
            or value.startswith(("\\\\", "//"))):
        _fail("path-unsupported", "evidence must use an absolute local regular-file path")
    path = Path(value)
    if not path.is_absolute():
        _fail("path-unsupported", "relative evidence paths are not admissible")
    if os.name == "nt":
        import ctypes

        # UNC/device paths were refused before querying the volume. An alternate
        # data stream is not an independently addressed regular evidence file.
        if any(":" in part for part in path.parts[1:]):
            _fail("path-unsupported", "alternate data stream paths are unsupported")
        drive_type = ctypes.windll.kernel32.GetDriveTypeW(str(path.anchor))
        if drive_type in (0, 1, 4):
            _fail("path-unsupported", "evidence volume is unavailable or remote")
    # Check each ancestor before following it. This is a local path policy, not
    # a filesystem lease against privileged concurrent replacements.
    for part in (*reversed(path.parents), path):
        observed = part.lstat()
        if (stat.S_ISLNK(observed.st_mode)
                or getattr(observed, "st_file_attributes", 0) & 0x400):
            _fail("path-unsupported", "symlink and reparse evidence paths are unsupported")
    if not stat.S_ISREG(path.stat().st_mode):
        _fail("path-unsupported", "evidence must be a regular file")
    return path


def _snapshot(path: str, resource: str) -> FileSnapshot:
    try:
        raw = _local_path(path).read_bytes()
    except (OSError, ValueError) as error:
        raise EvaluationAdmissionError(resource + "-unreadable", str(error)) from error
    return FileSnapshot(path, resource, raw, "sha256:" + sha256(raw).hexdigest())


def _strings(value: object, label: str, *, nonempty: bool = False) -> tuple[str, ...]:
    if type(value) is not list or (nonempty and not value):
        raise EvaluationError(label + " must be an array" + (" with entries" if nonempty else ""))
    return tuple(_require_identifier(item, label) for item in value)


def _nullable_text(value: object, label: str) -> str | None:
    return None if value is None else _require_identifier(value, label)


def _nullable_number(value: object, label: str) -> float | None:
    if value is None:
        return None
    if type(value) not in (float, int) or not math.isfinite(float(value)):
        raise EvaluationError(label + " must be a finite number or null")
    return float(value)


def _nullable_sequence(value: object, label: str) -> int | None:
    if value is not None and (type(value) is not int or value < 1):
        raise EvaluationError(label + " must be a positive integer or null")
    return value


def _parse_record(document: Mapping[str, Any], raw: bytes) -> ParsedEvaluationRecord:
    schema = document.get("schema_version")
    if type(schema) is not int:
        raise EvaluationError("schema_version must be an integer")
    if schema not in (1, 2, 3, 4):
        _fail("evaluation-schema-unsupported", "unsupported evaluation schema")
    fields = set(_BASE_FIELDS)
    if schema >= 3:
        fields |= _SELECTION_FIELDS
    if schema == 4:
        fields |= {"promotion_subject", "promotion_subject_digest"}
    _exact_document(document, fields, "evaluation")
    descriptor = ChallengerDescriptor(**_exact_document(document["descriptor"], {
        "challenger_id", "parent_champion_id", "change_ref", "proposal_digest",
    }, "descriptor"))
    identities = EvaluationIdentities(**_exact_document(document["identities"], {
        "proposer_id", "builder_id", "evaluator_id",
    }, "identities"))
    fingerprint = _require_identifier(document["contract_fingerprint"], "contract fingerprint")
    if schema == 4:
        _require_digest(fingerprint, "contract fingerprint")
    holdout_fields = {"holdout_id", "ordering", "violations", "prediction_digest"}
    if schema >= 2:
        holdout_fields.add("evaluator_id")
    holdout = _exact_document(document["holdout"], holdout_fields, "holdout")
    ordering = _exact_document(holdout["ordering"], {
        "seal_sequence", "reveal_sequence", "valid",
    }, "holdout ordering")
    if type(ordering["valid"]) is not bool:
        raise EvaluationError("holdout ordering.valid must be boolean")
    parsed_holdout = ParsedHoldout(
        _require_identifier(holdout["holdout_id"], "holdout_id"),
        _nullable_text(holdout.get("evaluator_id"), "holdout evaluator"),
        _nullable_text(holdout["prediction_digest"], "prediction digest"),
        _nullable_sequence(ordering["seal_sequence"], "seal_sequence"),
        _nullable_sequence(ordering["reveal_sequence"], "reveal_sequence"),
        ordering["valid"], _strings(holdout["violations"], "holdout violations"),
    )
    if type(document["surfaces"]) is not list or not document["surfaces"]:
        raise EvaluationError("surfaces must be a nonempty array")
    surfaces = []
    for entry in document["surfaces"]:
        surface = _exact_document(entry, {
            "kind", "name", "baseline_samples", "candidate_samples", "artifact_refs",
        }, "surface")
        if type(surface["baseline_samples"]) is not list or type(surface["candidate_samples"]) is not list:
            raise EvaluationError("samples must be arrays")
        surfaces.append(SurfaceResult(
            SurfaceKind(surface["kind"]), surface["name"], tuple(surface["baseline_samples"]),
            tuple(surface["candidate_samples"]), _strings(surface["artifact_refs"], "artifact refs"),
        ))
    selection = requested = resolved = None
    scored = None
    if schema >= 3:
        selection = _require_identifier(document["selection_policy"], "selection_policy")
        requested = _nullable_text(document["requested_primary_held_out_name"], "requested primary")
        resolved = _nullable_text(document["resolved_primary_held_out_name"], "resolved primary")
        scored = document["primary_scored"]
        if type(scored) is not bool:
            raise EvaluationError("primary_scored must be boolean")
    subject = subject_digest = None
    if schema == 4:
        subject = PromptEvaluationSubject.from_document(document["promotion_subject"])
        subject_digest = _require_digest(document["promotion_subject_digest"], "subject digest")
    return ParsedEvaluationRecord(
        schema, _require_identifier(document["evaluation_id"], "evaluation_id"),
        canonical_digest(document), raw, canonical_bytes(document), descriptor, identities,
        fingerprint, EvaluationVerdict(document["verdict"]),
        _strings(document["reasons"], "reasons", nonempty=True),
        _nullable_number(document["primary_effect"], "primary_effect"),
        _nullable_number(document["required_effect"], "required_effect"),
        _nullable_number(document["noise_floor"], "noise_floor"), parsed_holdout,
        tuple(surfaces), selection, requested, resolved, scored, subject, subject_digest,
    )


def load_evaluation_record(reference: EvaluationRecordReference) -> ParsedEvaluationRecord:
    """Inspect canonical receipts, including legacy and retained losing records."""
    if not isinstance(reference, EvaluationRecordReference):
        _fail("evaluation-malformed", "reference must be an EvaluationRecordReference")
    snapshot = _snapshot(reference.record_path, "evaluation")
    document = _json_document(snapshot.raw_bytes, "evaluation")
    try:
        parsed = _parse_record(document, snapshot.raw_bytes)
    except (ValueError, TypeError, OverflowError, RecursionError) as error:
        raise EvaluationAdmissionError("evaluation-malformed", str(error)) from error
    preimage = dict(document)
    preimage.pop("evaluation_id")
    expected_id = "EVAL-" + canonical_digest(preimage)[7:23]
    if parsed.evaluation_id != expected_id or reference.evaluation_id != expected_id:
        _fail("evaluation-id-mismatch", "evaluation_id does not address its document preimage")
    if parsed.record_digest != reference.record_digest:
        _fail("evaluation-digest-mismatch", "record_digest does not match the complete document")
    return parsed


def _load_contract(reference: EvaluationRecordReference, fingerprint: str) -> tuple[EvaluationContract, FileSnapshot]:
    path = Path(reference.record_path).parent / "contracts" / (fingerprint[7:] + ".json")
    snapshot = _snapshot(str(path), "contract")
    document = _json_document(snapshot.raw_bytes, "contract")
    try:
        _exact_document(document, {
            "selection_policy", "primary_held_out_name", "minimum_repetitions",
            "noise_multiplier", "minimum_effect", "guardrails",
        }, "contract")
        if document["selection_policy"] != "exact-held-out-v1":
            raise EvaluationError("unsupported contract selection policy")
        if type(document["guardrails"]) is not list:
            raise EvaluationError("guardrails must be an array")
        guards = []
        for value in document["guardrails"]:
            guard = _exact_document(value, {"surface", "maximum_regression"}, "guardrail")
            guards.append(GuardrailSpec(SurfaceKind(guard["surface"]), guard["maximum_regression"]))
        contract = EvaluationContract(
            minimum_repetitions=document["minimum_repetitions"],
            noise_multiplier=document["noise_multiplier"],
            minimum_effect=document["minimum_effect"], guardrails=tuple(guards),
            primary_held_out_name=document["primary_held_out_name"],
        )
        if canonical_bytes(contract.document()) != canonical_bytes(document):
            raise EvaluationError("contract is not the exact supported preimage")
    except (ValueError, TypeError, OverflowError, RecursionError) as error:
        raise EvaluationAdmissionError("contract-malformed", str(error)) from error
    if contract.fingerprint != fingerprint:
        _fail("contract-mismatch", "contract fingerprint does not address its preimage")
    return contract, snapshot


def resolve_keep_evidence(
    subject: PromptEvaluationSubject, reference: EvaluationRecordReference, *, evaluator_id: str,
) -> ResolvedKeepEvidence:
    """Recompute sufficient recorded KEEP evidence; this grants no activation right."""
    return resolve_decision_evidence(subject, reference, evaluator_id=evaluator_id,
                                     verdict=EvaluationVerdict.KEEP)


def resolve_decision_evidence(
    subject: PromptEvaluationSubject, reference: EvaluationRecordReference, *,
    evaluator_id: str, verdict: EvaluationVerdict,
) -> ResolvedKeepEvidence:
    """Authenticate no actors; reproduce the exact retained verdict, including losses.

    Quarantine with an absent seal remains admissible adverse evidence when its
    record, contract and referenced artifacts are intact. Missing artifacts stay
    inspectable through load_evaluation_record, but grant no action authority.
    """
    if not isinstance(subject, PromptEvaluationSubject):
        _fail("subject-mismatch", "subject must be a PromptEvaluationSubject")
    record = load_evaluation_record(reference)
    if record.schema_version != 4:
        _fail("evaluation-schema-not-admissible", "legacy receipts remain readable but cannot authorize KEEP")
    if record.verdict is not verdict:
        _fail("evaluation-not-keep" if verdict is EvaluationVerdict.KEEP else "evaluation-verdict-mismatch",
              "retained evaluation verdict is not " + verdict.value.upper())
    if (record.promotion_subject != subject
            or record.promotion_subject_digest != subject.subject_digest
            or record.descriptor != subject.descriptor):
        _fail("subject-mismatch", "record does not bind the exact declared subject")
    if (type(evaluator_id) is not str or not evaluator_id or evaluator_id != evaluator_id.strip()
            or record.identities.evaluator_id != evaluator_id
            or record.identities.proposer_id != subject.proposer_id
            or record.identities.builder_id != subject.builder_id
            or (verdict is EvaluationVerdict.KEEP and record.holdout.evaluator_id != evaluator_id)):
        _fail("identity-mismatch", "evaluation identity and seal bindings do not match")
    if record.contract_fingerprint != subject.contract_fingerprint:
        _fail("contract-mismatch", "subject and evaluation contract fingerprints differ")
    contract, contract_snapshot = _load_contract(reference, record.contract_fingerprint)
    refs = {ref for surface in record.surfaces for ref in surface.artifact_refs}
    if refs != set(subject.evidence_refs):
        _fail("subject-mismatch", "subject evidence references do not exactly cover surface references")
    snapshots = [FileSnapshot(reference.record_path, "evaluation", record.raw_bytes,
                              "sha256:" + sha256(record.raw_bytes).hexdigest()), contract_snapshot]
    for ref in subject.evidence_refs:
        path, separator, digest = ref.rpartition("#")
        try:
            if not separator or not path:
                raise EvaluationError("artifact reference must be path#sha256:<digest>")
            _require_digest(digest, "artifact digest")
        except EvaluationError as error:
            raise EvaluationAdmissionError("artifact-mismatch", str(error)) from error
        snapshot = _snapshot(path, "artifact")
        if snapshot.raw_digest != digest:
            _fail("artifact-mismatch", "retained surface artifact bytes do not match their digest")
        snapshots.append(snapshot)
    holdout = record.holdout
    if holdout.prediction_digest is not None or verdict is EvaluationVerdict.KEEP:
        try:
            _require_digest(holdout.prediction_digest, "holdout prediction digest")
        except EvaluationError as error:
            raise EvaluationAdmissionError("evaluation-not-keep", str(error)) from error
    valid = (holdout.valid is True and not holdout.violations
             and holdout.seal_sequence is not None
             and holdout.prediction_digest is not None and holdout.evaluator_id is not None
             and (holdout.reveal_sequence is None or holdout.reveal_sequence > holdout.seal_sequence))
    ordered = tuple(sorted(record.surfaces, key=lambda item: (item.kind.value, item.name)))
    if ordered != record.surfaces:
        _fail("evaluation-derived-fields-mismatch", "surface order is not the producer's canonical order")
    try:
        result = _score_evaluation(
            ordered, contract,
            ordering={"valid": valid, "seal_sequence": holdout.seal_sequence,
                      "reveal_sequence": holdout.reveal_sequence},
            violations=holdout.violations, seal_evaluator_id=holdout.evaluator_id,
            evaluator_id=evaluator_id, artifact_issues={},
        )
    except (ValueError, TypeError, OverflowError) as error:
        raise EvaluationAdmissionError("evaluation-malformed", str(error)) from error
    if result["verdict"] is not verdict:
        code = ("evaluation-insufficient" if any(
            reason.startswith(("missing surfaces:", "insufficient repeated measurements:"))
            for reason in result["reasons"]
        ) else "evaluation-not-keep") if verdict is EvaluationVerdict.KEEP else "evaluation-verdict-mismatch"
        _fail(code, "recorded metrics do not recompute to " + verdict.value.upper())
    expected = {
        "reasons": tuple(dict.fromkeys(result["reasons"])),
        "primary_effect": result["primary_effect"], "required_effect": result["required_effect"],
        "noise_floor": result["noise_floor"], "selection_policy": result["selection_policy"],
        "requested_primary_held_out_name": result["requested_primary"],
        "resolved_primary_held_out_name": result["resolved_primary"],
        "primary_scored": result["primary_effect"] is not None,
    }
    if any(getattr(record, key) != value for key, value in expected.items()):
        _fail("evaluation-derived-fields-mismatch", "retained scores or selection differ from recomputation")
    resolved = ResolvedKeepEvidence(subject, reference, record, contract, tuple(snapshots))
    # Do not return success when a file changed during the preceding reads.
    recheck_resolved_evidence(resolved)
    return resolved


def recheck_resolved_evidence(resolved: ResolvedKeepEvidence) -> None:
    """Reobserve only located record/contract/surface bytes, never prompt paths."""
    if not isinstance(resolved, ResolvedKeepEvidence):
        _fail("evaluation-malformed", "expected resolved KEEP evidence")
    for prior in resolved.snapshots:
        current = _snapshot(prior.path, prior.resource)
        if current.raw_bytes != prior.raw_bytes or current.raw_digest != prior.raw_digest:
            code = "evaluation-digest-mismatch" if prior.resource == "evaluation" else prior.resource + "-mismatch"
            _fail(code, "evidence changed after resolution: " + prior.path)
