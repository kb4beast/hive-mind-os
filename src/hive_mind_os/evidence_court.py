"""Content-addressed evidence, pinned comparators, and disabled promotion IO."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable, Mapping, Protocol, Sequence

from .identity_attestation import (
    AttestationVerifier,
    PrincipalAttestation,
    TrustProfile,
    verify_role_assignments,
)
from .runtime_contracts import canonical_json_bytes, raw_sha256, require_digest, require_identifier, require_time


class EvidenceCourtError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ContentAddressedExhibit:
    digest: str
    media_type: str
    provenance: str
    byte_count: int

    @classmethod
    def capture(cls, content: bytes, *, media_type: str, provenance: str) -> "ContentAddressedExhibit":
        if not isinstance(content, bytes):
            raise EvidenceCourtError("exhibit content must be bytes")
        require_identifier(media_type, "media_type")
        require_identifier(provenance, "provenance")
        return cls(raw_sha256(content), media_type, provenance, len(content))


class EvidenceSet:
    """Scoreable exhibits keyed by content, never by repeated citations."""

    def __init__(self, exhibits: Sequence[ContentAddressedExhibit] = ()) -> None:
        self._exhibits: dict[str, ContentAddressedExhibit] = {}
        for exhibit in exhibits:
            self.add(exhibit)

    def add(self, exhibit: ContentAddressedExhibit) -> bool:
        if not isinstance(exhibit, ContentAddressedExhibit):
            raise EvidenceCourtError("evidence set accepts typed exhibits only")
        prior = self._exhibits.get(exhibit.digest)
        if prior is not None and prior != exhibit:
            raise EvidenceCourtError("one content digest has conflicting provenance metadata")
        self._exhibits[exhibit.digest] = exhibit
        return prior is None

    @property
    def unique_exhibits(self) -> tuple[ContentAddressedExhibit, ...]:
        return tuple(self._exhibits[key] for key in sorted(self._exhibits))

    @property
    def scoreable_count(self) -> int:
        return len(self._exhibits)


@dataclass(frozen=True, slots=True)
class ComparatorReceipt:
    comparator_id: str
    version: str
    artifact_digest: str
    source_uri: str
    retrieved_at: str
    license_id: str
    license_evidence_digest: str
    outcome_receipt_digest: str

    def __post_init__(self) -> None:
        for value, label in ((self.comparator_id, "comparator_id"), (self.version, "version"),
                             (self.source_uri, "source_uri"), (self.license_id, "license_id")):
            require_identifier(value, label)
        for value, label in ((self.artifact_digest, "artifact_digest"),
                             (self.license_evidence_digest, "license_evidence_digest"),
                             (self.outcome_receipt_digest, "outcome_receipt_digest")):
            require_digest(value, label)
        require_time(self.retrieved_at, "retrieved_at")
        if self.license_id.casefold() in {"unknown", "unavailable", "none"}:
            raise EvidenceCourtError("comparator license evidence is unresolved")

    @property
    def identity(self) -> str:
        return raw_sha256(canonical_json_bytes({
            "comparator_id": self.comparator_id, "version": self.version,
            "artifact_digest": self.artifact_digest,
        }))


class ComparatorRegistry:
    def __init__(self) -> None:
        self._records: dict[str, ComparatorReceipt] = {}

    def register(self, receipt: ComparatorReceipt) -> str:
        identity = receipt.identity
        prior = self._records.get(identity)
        if prior is not None and prior != receipt:
            raise EvidenceCourtError("pinned comparator identity has conflicting receipts")
        self._records[identity] = receipt
        return identity

    def resolve(self, identity: str) -> ComparatorReceipt:
        require_digest(identity, "comparator identity")
        try:
            return self._records[identity]
        except KeyError as error:
            raise EvidenceCourtError("comparator does not resolve to a pinned receipt") from error


@dataclass(frozen=True, slots=True)
class HeldOutOutcomeReceipt:
    holdout_digest: str
    prediction_digest: str
    outcome_digest: str
    passed: int
    total: int
    receipt_digest: str


def evaluate_held_out(
    *, sealed_case_digest: str, prediction: Mapping[str, Any], outcomes: Mapping[str, Any],
) -> HeldOutOutcomeReceipt:
    """Evaluate revealed outcomes against a prior prediction with a reproducible receipt."""

    require_digest(sealed_case_digest, "sealed holdout digest")
    if not prediction or set(prediction) != set(outcomes):
        raise EvidenceCourtError("held-out prediction and outcome cases must match exactly")
    prediction_digest = raw_sha256(canonical_json_bytes(prediction))
    outcome_digest = raw_sha256(canonical_json_bytes(outcomes))
    passed = sum(prediction[key] == outcomes[key] for key in sorted(prediction))
    document = {
        "holdout_digest": sealed_case_digest, "prediction_digest": prediction_digest,
        "outcome_digest": outcome_digest, "passed": passed, "total": len(prediction),
    }
    return HeldOutOutcomeReceipt(
        sealed_case_digest, prediction_digest, outcome_digest, passed, len(prediction),
        raw_sha256(canonical_json_bytes(document)),
    )


@dataclass(frozen=True, slots=True)
class PromotionGrant:
    grant_id: str
    candidate_digest: str
    action: str
    authority_principal_id: str
    expires_at: str
    grant_digest: str

    def __post_init__(self) -> None:
        require_identifier(self.grant_id, "grant_id")
        require_digest(self.candidate_digest, "candidate_digest")
        require_identifier(self.authority_principal_id, "authority_principal_id")
        require_digest(self.grant_digest, "grant_digest")
        require_time(self.expires_at, "grant expiry")
        if self.action != "promote-candidate":
            raise EvidenceCourtError("promotion grant cannot authorize merge, push, or deploy")
        expected = raw_sha256(canonical_json_bytes({
            "grant_id": self.grant_id, "candidate_digest": self.candidate_digest,
            "action": self.action, "authority_principal_id": self.authority_principal_id,
            "expires_at": self.expires_at,
        }))
        if self.grant_digest != expected:
            raise EvidenceCourtError("promotion grant digest does not bind its authority fields")


class PromotionGrantVerifier(Protocol):
    def verify(self, grant: PromotionGrant) -> bool: ...


class PinnedPromotionGrantVerifier:
    """Authenticate grants against pins supplied outside the promotion request."""

    def __init__(self, pinned_grants: Mapping[str, str]) -> None:
        self._pins = dict(pinned_grants)
        if not self._pins:
            raise EvidenceCourtError("promotion authority requires at least one pinned grant")
        for grant_id, digest in self._pins.items():
            require_identifier(grant_id, "pinned grant id")
            require_digest(digest, "pinned grant digest")

    def verify(self, grant: PromotionGrant) -> bool:
        return self._pins.get(grant.grant_id) == grant.grant_digest


class PromotionAdapter:
    """Separately enabled, narrow promotion surface; disabled by default."""

    def __init__(
        self, *, enabled: bool = False, verifier: AttestationVerifier | None = None,
        grant_verifier: PromotionGrantVerifier | None = None,
        sink: Callable[[str], Any] | None = None,
    ) -> None:
        self.enabled = enabled
        self.verifier = verifier
        self.grant_verifier = grant_verifier
        self.sink = sink

    def promote(
        self, candidate_digest: str, *, grant: PromotionGrant | None = None,
        role_attestations: Mapping[str, PrincipalAttestation] | None = None,
    ) -> dict[str, Any]:
        require_digest(candidate_digest, "candidate digest")
        if not self.enabled or self.sink is None or self.verifier is None:
            raise EvidenceCourtError("promotion adapter is disabled; no candidate was promoted")
        if self.grant_verifier is None:
            raise EvidenceCourtError("promotion requires a separately authenticated authority grant")
        if self.verifier.profile is not TrustProfile.INDEPENDENT_PRINCIPALS:
            raise EvidenceCourtError("promotion requires independently administered principals")
        if grant is None or role_attestations is None:
            raise EvidenceCourtError("promotion requires a separately authenticated authority grant")
        if not self.grant_verifier.verify(grant):
            raise EvidenceCourtError("promotion grant is not authenticated by configured authority")
        if require_time(grant.expires_at, "grant expiry") <= datetime.now(UTC):
            raise EvidenceCourtError("promotion grant expired")
        bindings = verify_role_assignments(
            role_attestations, verifier=self.verifier,
            independently_administered=(("verifier", "promoter"),),
        )
        if grant.candidate_digest != candidate_digest or bindings["promoter"] != grant.authority_principal_id:
            raise EvidenceCourtError("promotion grant is not bound to this candidate and promoter")
        result = self.sink(candidate_digest)
        receipt = {
            "status": "PROMOTED", "candidate_digest": candidate_digest,
            "grant_id": grant.grant_id, "grant_digest": grant.grant_digest,
            "verifier_principal_id": bindings["verifier"],
            "promoter_principal_id": bindings["promoter"], "result": result,
        }
        receipt["receipt_digest"] = raw_sha256(canonical_json_bytes(receipt))
        return receipt


__all__ = [
    "ComparatorReceipt", "ComparatorRegistry", "ContentAddressedExhibit",
    "EvidenceCourtError", "EvidenceSet", "HeldOutOutcomeReceipt", "PromotionAdapter",
    "PinnedPromotionGrantVerifier", "PromotionGrant", "PromotionGrantVerifier",
    "evaluate_held_out",
]
