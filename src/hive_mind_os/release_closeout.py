"""N33 evidence-to-release closeout builder."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

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
