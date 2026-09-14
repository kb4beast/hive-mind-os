"""Executable N29 failure and disclosure attack harness."""
from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence

from .whole_os_qualification import (
    AdversarialReport, EvidenceRef, FailureObservation, FailurePoint,
)


MANDATORY_BOUNDARIES = (
    "tenant-collision", "mount-escape", "host-file-read", "denied-egress",
    "secret-inheritance", "private-embedding", "provider-payload",
    "artifact-extraction", "lesson-export", "pr-metadata", "logs-errors",
    "endpoint-git-objects", "endpoint-source-mirrors", "draft-activation",
    "stale-holdout", "same-actor-review", "hidden-failure-deletion",
    "self-upgrade-rollback",
)


class AdversarialAdapter(Protocol):
    identity: str

    def inject(self, effect_class: str, point: FailurePoint, candidate_digest: str) -> FailureObservation: ...
    def attack_boundary(self, boundary: str, candidate_digest: str) -> EvidenceRef: ...


@dataclass(frozen=True, slots=True)
class Canary:
    canary_id: str
    secret: bytes

    def variants(self) -> tuple[bytes, ...]:
        encoded = base64.b64encode(self.secret)
        hexadecimal = self.secret.hex().encode("ascii")
        return self.secret, encoded, hexadecimal


class CanaryScanner:
    """Scans exact, encoded, and split forms across an outbound artifact set."""

    def __init__(self, canaries: Sequence[Canary]) -> None:
        if not canaries or len({item.canary_id for item in canaries}) != len(canaries):
            raise ValueError("unique canaries are required")
        self.canaries = tuple(canaries)

    def scan(self, artifacts: Mapping[str, bytes]) -> Mapping[str, tuple[str, ...]]:
        ordered = b"\x00".join(artifacts[key] for key in sorted(artifacts))
        compact = b"".join(artifacts[key] for key in sorted(artifacts))
        findings: dict[str, tuple[str, ...]] = {}
        for canary in self.canaries:
            hit = []
            for path, body in artifacts.items():
                if any(variant in body for variant in canary.variants()):
                    hit.append(path)
            if any(variant in ordered or variant in compact for variant in canary.variants()):
                hit.append("<cross-artifact>")
            if hit:
                findings[canary.canary_id] = tuple(sorted(set(hit)))
        return findings

    def require_clean(self, artifacts: Mapping[str, bytes]) -> None:
        findings = self.scan(artifacts)
        if findings:
            raise ValueError(f"outbound canary disclosure detected: {sorted(findings)}")


class AdversarialHarness:
    def __init__(self, adapter: AdversarialAdapter) -> None:
        if not getattr(adapter, "identity", ""):
            raise ValueError("adversarial adapter identity is required")
        self.adapter = adapter

    def run(
        self, *, candidate_digest: str, effect_classes: Sequence[str],
        residual_risks: Sequence[str] = (), real_backend_evidence: Sequence[EvidenceRef] = (),
    ) -> AdversarialReport:
        if not candidate_digest.startswith("sha256:") or len(candidate_digest) != 71:
            raise ValueError("candidate digest must be pinned")
        if not effect_classes or len(set(effect_classes)) != len(effect_classes):
            raise ValueError("at least one durable effect class is required")
        observations = tuple(
            self.adapter.inject(effect, point, candidate_digest)
            for effect in effect_classes for point in FailurePoint
        )
        boundary_evidence = tuple(
            self.adapter.attack_boundary(boundary, candidate_digest)
            for boundary in MANDATORY_BOUNDARIES
        )
        if len(boundary_evidence) != len(MANDATORY_BOUNDARIES) or len({item.digest for item in boundary_evidence}) != len(MANDATORY_BOUNDARIES):
            raise ValueError("boundary attacks require distinct evidence receipts")
        return AdversarialReport(
            candidate_digest=candidate_digest,
            effect_classes=tuple(effect_classes), observations=observations,
            attempted_boundaries=MANDATORY_BOUNDARIES,
            residual_risks=tuple(residual_risks),
            real_backend_evidence=tuple(real_backend_evidence),
        )
