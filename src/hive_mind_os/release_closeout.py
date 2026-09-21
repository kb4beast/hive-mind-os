"""N33 evidence-to-release closeout builder."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from .production_evidence import (
    EvidenceBlocker,
    EvidencePurpose,
    EvidenceResolution,
    EvidenceUse,
    ProductionEvidenceContext,
    ProductionEvidenceError,
)
from .whole_os_qualification import (
    LIFECYCLE_STAGE_IDS,
    NODE_IDS,
    REQUIREMENT_IDS,
    SPECIALIST_ROLE_IDS,
    CloseoutAssessment,
    CloseoutManifest,
    Disposition,
    EvidenceKind,
    EvidenceRef,
    ExternalObligation,
    OperationalReceipt,
    QualificationError,
    canonical_digest,
)


class CloseoutBuilder:
    def __init__(
        self,
        *,
        release_id: str,
        candidate_digest: str,
        previous_release_digest: str,
        builder_id: str,
    ) -> None:
        for value, name in ((release_id, "release"), (builder_id, "builder")):
            if (
                type(value) is not str
                or not value
                or value != value.strip()
                or any(character.isspace() for character in value)
            ):
                raise ValueError(f"{name} identity is required")
        self.release_id = release_id
        self.candidate_digest = candidate_digest
        self.previous_release_digest = previous_release_digest
        self.builder_id = builder_id
        self.requirements: dict[str, CloseoutAssessment] = {}
        self.nodes: dict[str, CloseoutAssessment] = {}
        self.obligations: dict[str, ExternalObligation] = {}
        self.roles: dict[str, tuple[EvidenceRef, ...]] = {}
        self.lifecycle: dict[str, tuple[EvidenceRef, ...]] = {}

    def record_requirement(
        self,
        requirement_id: str,
        disposition: Disposition,
        evidence: Iterable[EvidenceRef] = (),
        *,
        obligation_ids: Iterable[str] = (),
        rationale: str = "",
    ) -> None:
        if requirement_id not in REQUIREMENT_IDS:
            raise ValueError("unknown whole-OS requirement")
        assessment = CloseoutAssessment(
            requirement_id,
            disposition,
            tuple(evidence),
            tuple(obligation_ids),
            rationale,
        )
        if (
            requirement_id in self.requirements
            and self.requirements[requirement_id] != assessment
        ):
            raise ValueError("requirement evidence is append-only")
        self.requirements[requirement_id] = assessment

    def disposition_node(
        self,
        node_id: str,
        disposition: Disposition,
        evidence: Iterable[EvidenceRef] = (),
        *,
        obligation_ids: Iterable[str] = (),
        rationale: str = "",
    ) -> None:
        if node_id not in NODE_IDS:
            raise ValueError("unknown campaign node")
        assessment = CloseoutAssessment(
            node_id,
            disposition,
            tuple(evidence),
            tuple(obligation_ids),
            rationale,
        )
        previous = self.nodes.get(node_id)
        if previous is not None and previous != assessment:
            raise ValueError("node disposition requires a successor closeout")
        self.nodes[node_id] = assessment

    def add_obligation(self, obligation: ExternalObligation) -> None:
        previous = self.obligations.get(obligation.obligation_id)
        if previous is not None and previous != obligation:
            raise ValueError("obligation identity already has different content")
        self.obligations[obligation.obligation_id] = obligation

    def record_role(self, role_id: str, evidence: Iterable[EvidenceRef]) -> None:
        self._record_evidence(self.roles, SPECIALIST_ROLE_IDS, role_id, evidence, "role")

    def record_lifecycle_stage(
        self, stage_id: str, evidence: Iterable[EvidenceRef]
    ) -> None:
        self._record_evidence(
            self.lifecycle,
            LIFECYCLE_STAGE_IDS,
            stage_id,
            evidence,
            "lifecycle stage",
        )

    @staticmethod
    def _record_evidence(
        target: dict[str, tuple[EvidenceRef, ...]],
        allowed: frozenset[str],
        subject_id: str,
        evidence: Iterable[EvidenceRef],
        label: str,
    ) -> None:
        if subject_id not in allowed:
            raise ValueError(f"unknown {label}")
        values = tuple(evidence)
        if not values:
            raise ValueError(f"{label} evidence is required")
        if any(item.kind is EvidenceKind.SYNTHETIC for item in values):
            raise ValueError(f"{label} evidence must be attested")
        previous = target.get(subject_id)
        if previous is not None and previous != values:
            raise ValueError(f"{label} evidence is append-only")
        target[subject_id] = values

    def missing(self) -> dict[str, tuple[str, ...]]:
        return {
            "requirements": tuple(
                item for item in REQUIREMENT_IDS if item not in self.requirements
            ),
            "nodes": tuple(item for item in NODE_IDS if item not in self.nodes),
            "roles": tuple(
                item for item in sorted(SPECIALIST_ROLE_IDS) if item not in self.roles
            ),
            "lifecycle": tuple(
                item for item in sorted(LIFECYCLE_STAGE_IDS)
                if item not in self.lifecycle
            ),
        }

    def seal(
        self,
        *,
        startup_receipt: OperationalReceipt,
        rollback_receipt: OperationalReceipt,
        independent_judge_id: str,
        final_disposition: Disposition,
        final_rationale: str,
        sealed_at: int,
    ) -> CloseoutManifest:
        if (
            not independent_judge_id.strip()
            or independent_judge_id == self.builder_id
            or not final_rationale.strip()
            or type(sealed_at) is not int
            or sealed_at < 0
        ):
            raise ValueError(
                "independent judge, final rationale and seal timestamp are required"
            )
        missing = self.missing()
        if any(missing.values()):
            raise ValueError(f"closeout is incomplete: {missing}")
        manifest = CloseoutManifest(
            self.release_id,
            self.candidate_digest,
            self.previous_release_digest,
            dict(self.requirements),
            dict(self.nodes),
            tuple(self.obligations.values()),
            dict(self.roles),
            dict(self.lifecycle),
            startup_receipt,
            rollback_receipt,
            self.builder_id,
            independent_judge_id,
            final_disposition,
            final_rationale,
            sealed_at,
        )
        return manifest


def write_release_manifest(path: str | Path, manifest: CloseoutManifest) -> str:
    document = {"schema_version": 1, **asdict(manifest)}
    document["manifest_digest"] = canonical_digest(document)
    encoded = (
        json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    )
    target = Path(path)
    if target.exists():
        existing = target.read_text(encoding="utf-8")
        if existing != encoded:
            raise ValueError("versioned release manifest is immutable")
        return document["manifest_digest"]
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(encoded, encoding="utf-8")
    temporary.replace(target)
    return document["manifest_digest"]


def load_release_manifest(path: str | Path) -> tuple[CloseoutManifest, str]:
    """Load a manifest only when its embedded digest matches its content."""
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
        supplied = document.pop("manifest_digest")
        expected = canonical_digest(document)
        if supplied != expected:
            raise ValueError("release manifest digest mismatch")
        if set(document) != {
            "schema_version",
            "release_id",
            "candidate_digest",
            "previous_release_digest",
            "requirement_assessments",
            "node_assessments",
            "obligations",
            "role_evidence",
            "lifecycle_evidence",
            "startup_receipt",
            "rollback_receipt",
            "builder_id",
            "independent_judge_id",
            "final_disposition",
            "final_rationale",
            "sealed_at",
        } or document["schema_version"] != 1:
            raise ValueError("release manifest schema is not closed")
        requirements = {
            key: _load_assessment(value)
            for key, value in document["requirement_assessments"].items()
        }
        nodes = {
            key: _load_assessment(value)
            for key, value in document["node_assessments"].items()
        }
        obligations = tuple(
            ExternalObligation(
                item["obligation_id"],
                Disposition(item["kind"]),
                item["description"],
                tuple(item["blocks_claims"]),
            )
            for item in document["obligations"]
        )
        roles = {
            key: tuple(_load_evidence(item) for item in values)
            for key, values in document["role_evidence"].items()
        }
        lifecycle = {
            key: tuple(_load_evidence(item) for item in values)
            for key, values in document["lifecycle_evidence"].items()
        }
        manifest = CloseoutManifest(
            document["release_id"],
            document["candidate_digest"],
            document["previous_release_digest"],
            requirements,
            nodes,
            obligations,
            roles,
            lifecycle,
            _load_operational_receipt(document["startup_receipt"]),
            _load_operational_receipt(document["rollback_receipt"]),
            document["builder_id"],
            document["independent_judge_id"],
            Disposition(document["final_disposition"]),
            document["final_rationale"],
            document["sealed_at"],
        )
        return manifest, supplied
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        if (
            isinstance(exc, ValueError)
            and str(exc) == "release manifest digest mismatch"
        ):
            raise
        raise ValueError("release manifest is corrupt") from exc


def manifest_digest(manifest: CloseoutManifest) -> str:
    """Recompute the embedded manifest digest exactly as ``write_release_manifest`` does:
    ``whole_os_qualification.canonical_digest`` over the document including
    ``schema_version`` and excluding ``manifest_digest``. Never a kernel or file-byte
    digest."""
    return canonical_digest({"schema_version": 1, **asdict(manifest)})


@dataclass(frozen=True, slots=True)
class VerifiedCloseout:
    """An audit observation of one verification, not a capability or admission token."""

    manifest_digest: str
    release_id: str
    candidate_digest: str
    final_disposition: Disposition
    independent_judge_id: str
    resolution_digests: tuple[str, ...]
    verified_at: int

    @property
    def positive(self) -> bool:
        return self.final_disposition in {Disposition.ADOPT, Disposition.ADAPT}


def _closeout_entries(
    manifest: CloseoutManifest, digest: str, judgment: EvidenceRef
) -> list[tuple[EvidenceRef, EvidenceUse]]:
    """Every nested reference is walked, including negative dispositions. The detached
    final judgment is last; it cannot live inside the manifest it signs."""
    release, candidate = manifest.release_id, manifest.candidate_digest
    entries: list[tuple[EvidenceRef, EvidenceUse]] = []

    def add(
        ref: EvidenceRef,
        purpose: EvidencePurpose,
        subject_id: str,
        claims: dict[str, object],
        *,
        window_start: int | None = None,
    ) -> None:
        entries.append(
            (
                ref,
                EvidenceUse(
                    purpose, subject_id, release, candidate, None, claims,
                    window_start=window_start,
                ),
            )
        )

    for purpose, assessments in (
        (EvidencePurpose.CLOSEOUT_REQUIREMENT, manifest.requirement_assessments),
        (EvidencePurpose.CLOSEOUT_NODE, manifest.node_assessments),
    ):
        for key in sorted(assessments):
            assessment = assessments[key]
            for ref in assessment.evidence:
                add(
                    ref,
                    purpose,
                    assessment.subject_id,
                    {
                        "disposition": assessment.disposition.value,
                        "obligation_ids": sorted(assessment.obligation_ids),
                    },
                )
    for role_id in sorted(manifest.role_evidence):
        for ref in manifest.role_evidence[role_id]:
            add(ref, EvidencePurpose.CLOSEOUT_ROLE, role_id, {"role_id": role_id})
    for stage_id in sorted(manifest.lifecycle_evidence):
        for ref in manifest.lifecycle_evidence[stage_id]:
            add(ref, EvidencePurpose.CLOSEOUT_STAGE, stage_id, {"stage_id": stage_id})
    for purpose, receipt in (
        (EvidencePurpose.CLOSEOUT_STARTUP, manifest.startup_receipt),
        (EvidencePurpose.CLOSEOUT_ROLLBACK, manifest.rollback_receipt),
    ):
        add(
            receipt.evidence,
            purpose,
            receipt.candidate_digest,
            {"argv": list(receipt.argv), "exit_code": receipt.exit_code},
        )
    add(
        judgment,
        EvidencePurpose.CLOSEOUT_JUDGMENT,
        release,
        {
            "manifest_digest": digest,
            "release_id": release,
            "previous_release_digest": manifest.previous_release_digest,
            "sealed_at": manifest.sealed_at,
            "final_disposition": manifest.final_disposition.value,
            "independent_judge_id": manifest.independent_judge_id,
        },
        window_start=manifest.sealed_at,
    )
    return entries


def verify_production_closeout(
    manifest: CloseoutManifest,
    supplied_digest: str,
    judgment: EvidenceRef,
    context: ProductionEvidenceContext,
) -> VerifiedCloseout:
    """Guarded verification that always walks the loaded content, so an existing file or
    a raw structural load can never stand in for it. Raises a typed blocker and appends a
    local audit record either way."""
    snapshot = _validated_snapshot(manifest, context)
    return _verify_snapshot(snapshot, supplied_digest, judgment, context)


def _copy_evidence(item: object) -> EvidenceRef:
    if type(item) is not EvidenceRef:
        raise TypeError("closeout evidence must be typed evidence references")
    return EvidenceRef(item.uri, item.digest, item.kind, item.subject_id, item.observed_at)


def _copy_assessment(item: object) -> CloseoutAssessment:
    if type(item) is not CloseoutAssessment:
        raise TypeError("closeout assessments must be typed assessments")
    return CloseoutAssessment(
        item.subject_id,
        item.disposition,
        tuple(_copy_evidence(ref) for ref in tuple(item.evidence)),
        tuple(item.obligation_ids),
        item.rationale,
    )


def _copy_operation(item: object) -> OperationalReceipt:
    if type(item) is not OperationalReceipt:
        raise TypeError("operational receipts must be typed")
    return OperationalReceipt(
        tuple(item.argv), item.candidate_digest, item.exit_code, _copy_evidence(item.evidence)
    )


def _copy_map(value: object, copy) -> dict:
    if not isinstance(value, dict):
        raise TypeError("closeout collections must be mappings")
    return {key: copy(item) for key, item in dict(value).items()}


def snapshot_manifest(manifest: CloseoutManifest) -> CloseoutManifest:
    """Return a validated, stable deep copy built through the unchanged
    ``CloseoutManifest`` constructor, so every existing schema and acceptance rule is
    re-applied to the content that will actually be verified, digested and written. Later
    mutation of the caller's public mappings cannot reach the copy."""
    try:
        if type(manifest) is not CloseoutManifest:
            raise TypeError("a CloseoutManifest is required")
        obligations = manifest.obligations
        if not isinstance(obligations, tuple) or any(
            type(item) is not ExternalObligation for item in obligations
        ):
            raise TypeError("closeout obligations must be a tuple of typed obligations")
        return CloseoutManifest(
            manifest.release_id,
            manifest.candidate_digest,
            manifest.previous_release_digest,
            _copy_map(manifest.requirement_assessments, _copy_assessment),
            _copy_map(manifest.node_assessments, _copy_assessment),
            tuple(
                ExternalObligation(
                    item.obligation_id, item.kind, item.description, tuple(item.blocks_claims)
                )
                for item in obligations
            ),
            _copy_map(
                manifest.role_evidence,
                lambda values: tuple(_copy_evidence(ref) for ref in tuple(values)),
            ),
            _copy_map(
                manifest.lifecycle_evidence,
                lambda values: tuple(_copy_evidence(ref) for ref in tuple(values)),
            ),
            _copy_operation(manifest.startup_receipt),
            _copy_operation(manifest.rollback_receipt),
            manifest.builder_id,
            manifest.independent_judge_id,
            manifest.final_disposition,
            manifest.final_rationale,
            manifest.sealed_at,
        )
    except (QualificationError, ValueError, TypeError, AttributeError, KeyError) as error:
        raise ProductionEvidenceError(
            EvidenceBlocker.MANIFEST_MALFORMED, f"manifest structure is invalid: {error}"
        ) from error


def _validated_snapshot(
    manifest: CloseoutManifest, context: ProductionEvidenceContext
) -> CloseoutManifest:
    """The single structural gate every production boundary passes before any evidence
    is resolved, any audit success is recorded or any file is written."""
    if type(context) is not ProductionEvidenceContext:
        raise ProductionEvidenceError(
            EvidenceBlocker.POLICY_INVALID, "a production evidence context is required"
        )
    try:
        return snapshot_manifest(manifest)
    except ProductionEvidenceError as error:
        context.record_failure("closeout", error)
        raise


def _verify_snapshot(
    manifest: CloseoutManifest,
    supplied_digest: str,
    judgment: EvidenceRef,
    context: ProductionEvidenceContext,
) -> VerifiedCloseout:
    scope = "closeout"
    try:
        now = context.now()
        recomputed = manifest_digest(manifest)
        if supplied_digest != recomputed:
            raise ProductionEvidenceError(
                EvidenceBlocker.DIGEST_MISMATCH,
                "manifest digest does not match the recomputed canonical digest",
            )
        if manifest.sealed_at > now:
            raise ProductionEvidenceError(EvidenceBlocker.TIME_WINDOW, "manifest is sealed in the future")
        policy = context.resolver.policy
        if policy is None:
            raise ProductionEvidenceError(
                EvidenceBlocker.TRUST_STORE_MISSING, "no evidence trust policy is configured"
            )
        builder, judge = policy.require_separation(
            manifest.builder_id, manifest.independent_judge_id
        )
        entries = _closeout_entries(manifest, recomputed, judgment)
    except ProductionEvidenceError as error:
        context.record_failure(scope, error)
        raise

    def check(resolutions: tuple[EvidenceResolution, ...]) -> None:
        *nested, final = resolutions
        if (
            final.purpose is not EvidencePurpose.CLOSEOUT_JUDGMENT
            or final.issuer_id != manifest.independent_judge_id
        ):
            raise ProductionEvidenceError(
                EvidenceBlocker.SEPARATION, "the final judgment was not issued by the sealed judge"
            )
        for item in nested:
            if (
                item.issuer_id in {judge.principal_id, builder.principal_id}
                or item.administration_id == judge.administration_id
                or item.public_key_digest == judge.public_key_digest
            ):
                raise ProductionEvidenceError(
                    EvidenceBlocker.SEPARATION,
                    "the judge or builder principal also attested nested closeout evidence",
                )

    resolutions = context.verify(scope, entries, now=now, after=check)
    return VerifiedCloseout(
        recomputed,
        manifest.release_id,
        manifest.candidate_digest,
        manifest.final_disposition,
        manifest.independent_judge_id,
        tuple(item.digest() for item in resolutions),
        now,
    )


def write_verified_release_manifest(
    path: str | Path,
    manifest: CloseoutManifest,
    judgment: EvidenceRef,
    context: ProductionEvidenceContext,
) -> VerifiedCloseout:
    """Production write: snapshot and validate once, verify that same content, then write
    that same content. The existing-file early return in ``write_release_manifest`` cannot
    bypass evidence resolution, and the caller's mutable manifest is never re-read."""
    snapshot = _validated_snapshot(manifest, context)
    verified = _verify_snapshot(snapshot, manifest_digest(snapshot), judgment, context)
    if write_release_manifest(path, snapshot) != verified.manifest_digest:
        raise ProductionEvidenceError(
            EvidenceBlocker.DIGEST_MISMATCH, "written manifest digest differs from the verified one"
        )
    return verified


def load_verified_release_manifest(
    path: str | Path, judgment: EvidenceRef, context: ProductionEvidenceContext
) -> tuple[CloseoutManifest, VerifiedCloseout]:
    """Production load: the structural load is only the first step. The returned manifest
    is the validated snapshot that was verified."""
    manifest, digest = load_release_manifest(path)
    snapshot = _validated_snapshot(manifest, context)
    return snapshot, _verify_snapshot(snapshot, digest, judgment, context)


def _load_evidence(document: dict[str, object]) -> EvidenceRef:
    observed_at = document["observed_at"]
    if type(observed_at) is not int:
        raise TypeError("evidence timestamp must be an integer")
    return EvidenceRef(
        str(document["uri"]),
        str(document["digest"]),
        EvidenceKind(str(document["kind"])),
        str(document["subject_id"]),
        observed_at,
    )


def _load_assessment(document: dict[str, object]) -> CloseoutAssessment:
    evidence_rows = document["evidence"]
    obligation_rows = document["obligation_ids"]
    if not isinstance(evidence_rows, list) or not isinstance(obligation_rows, list):
        raise TypeError("closeout assessment collections must be lists")
    return CloseoutAssessment(
        str(document["subject_id"]),
        Disposition(str(document["disposition"])),
        tuple(_load_evidence(item) for item in evidence_rows),
        tuple(str(item) for item in obligation_rows),
        str(document["rationale"]),
    )


def _load_operational_receipt(document: dict[str, object]) -> OperationalReceipt:
    argv = document["argv"]
    evidence = document["evidence"]
    exit_code = document["exit_code"]
    if (
        not isinstance(argv, list)
        or not isinstance(evidence, dict)
        or type(exit_code) is not int
    ):
        raise TypeError("operational receipt is malformed")
    return OperationalReceipt(
        tuple(str(item) for item in argv),
        str(document["candidate_digest"]),
        exit_code,
        _load_evidence(evidence),
    )
