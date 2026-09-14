"""Typed N28/N29/N31/N32/N33 qualification and closeout contracts.

The objects in this module record observations; they do not manufacture external
authority, runtime access, delivery receipts, elapsed pilot time, or a promotion.
Host integrations remain responsible for authenticating evidence references.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from hashlib import sha256
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence


class QualificationError(ValueError):
    """A closed qualification contract was violated."""


def canonical_digest(value: object) -> str:
    return "sha256:" + sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _id(value: object, name: str) -> None:
    if type(value) is not str or not value or value != value.strip() or any(c.isspace() for c in value):
        raise QualificationError(f"{name} must be an exact nonempty identifier")


def _digest(value: object, name: str) -> None:
    if type(value) is not str or len(value) != 71 or not value.startswith("sha256:") or set(value[7:]) - set("0123456789abcdef"):
        raise QualificationError(f"{name} must be a lowercase SHA-256 digest")


class EvidenceKind(StrEnum):
    SYNTHETIC = "synthetic"
    ATTESTED_REAL = "attested_real"
    EXTERNAL_RECEIPT = "external_receipt"


class Disposition(StrEnum):
    ADOPT = "adopt"
    ADAPT = "adapt"
    DEFER = "defer"
    REJECT = "reject"
    QUARANTINE = "quarantine"
    BLOCKED_CAPABILITY = "blocked_capability"
    BLOCKED_SOURCE = "blocked_source"
    BLOCKED_AUTHORITY = "blocked_authority"


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    uri: str
    digest: str
    kind: EvidenceKind
    subject_id: str
    observed_at: int

    def __post_init__(self) -> None:
        _id(self.uri, "evidence URI")
        _digest(self.digest, "evidence digest")
        _id(self.subject_id, "evidence subject")
        if type(self.kind) is not EvidenceKind or type(self.observed_at) is not int or self.observed_at < 0:
            raise QualificationError("evidence kind and timestamp must be typed")


@dataclass(frozen=True, slots=True)
class CapabilityDeclaration:
    profile_id: str
    language: str
    check_class: str
    runtime_supported: bool
    compile_supported: bool
    evidence: tuple[EvidenceRef, ...] = ()
    incomplete_reason: str | None = None

    def __post_init__(self) -> None:
        for name in ("profile_id", "language", "check_class"):
            _id(getattr(self, name), name)
        if type(self.runtime_supported) is not bool or type(self.compile_supported) is not bool:
            raise QualificationError("capability flags must be exact booleans")
        if not self.runtime_supported and not self.compile_supported:
            if type(self.incomplete_reason) is not str or not self.incomplete_reason.strip():
                raise QualificationError("unsupported capability requires a reason")
        elif self.incomplete_reason is not None:
            raise QualificationError("supported capability cannot carry an incomplete reason")
        if len(set(self.evidence)) != len(self.evidence):
            raise QualificationError("capability evidence must be unique")


REQUIRED_PROFILES = frozenset({"self-python", "external-python", "node-typescript", "go", "rust", "roblox"})


@dataclass(frozen=True, slots=True)
class CompositionManifest:
    candidate_digest: str
    configuration_digest: str
    profiles: tuple[CapabilityDeclaration, ...]
    component_digests: Mapping[str, str]
    legacy_plan_policy: str
    target_runtime_imports_hive: bool

    def __post_init__(self) -> None:
        _digest(self.candidate_digest, "candidate digest")
        _digest(self.configuration_digest, "configuration digest")
        ids = tuple(item.profile_id for item in self.profiles)
        if set(ids) != REQUIRED_PROFILES or len(ids) != len(set(ids)):
            raise QualificationError("composition must declare each required profile exactly once")
        if not self.component_digests:
            raise QualificationError("composition requires exact component digests")
        for name, digest in self.component_digests.items():
            _id(name, "component name"); _digest(digest, "component digest")
        if self.legacy_plan_policy not in {"refuse-ambiguous", "migrate-explicit-subject", "inert-only"}:
            raise QualificationError("legacy plan policy is not fail-closed")
        if self.target_runtime_imports_hive is not False:
            raise QualificationError("delivered applications must run without Hive")


class FailurePoint(StrEnum):
    BEFORE_INTENT = "before_intent"
    AFTER_INTENT = "after_intent"
    AFTER_EFFECT_BEFORE_RECEIPT = "after_effect_before_receipt"
    AFTER_RECEIPT_BEFORE_TRANSITION = "after_receipt_before_transition"
    LEASE_EXPIRY = "lease_expiry"
    STALE_WORKER_RETURN = "stale_worker_return"


@dataclass(frozen=True, slots=True)
class FailureObservation:
    effect_class: str
    point: FailurePoint
    candidate_digest: str
    healthy_path_passed: bool
    negative_control_rejected: bool
    resulting_effect_count: int
    evidence: EvidenceRef

    def __post_init__(self) -> None:
        _id(self.effect_class, "effect class")
        _digest(self.candidate_digest, "candidate digest")
        if type(self.point) is not FailurePoint:
            raise QualificationError("failure point must be typed")
        if type(self.healthy_path_passed) is not bool or type(self.negative_control_rejected) is not bool:
            raise QualificationError("failure observation flags must be booleans")
        if type(self.resulting_effect_count) is not int or self.resulting_effect_count < 0:
            raise QualificationError("resulting effect count must be nonnegative")


@dataclass(frozen=True, slots=True)
class AdversarialReport:
    candidate_digest: str
    effect_classes: tuple[str, ...]
    observations: tuple[FailureObservation, ...]
    attempted_boundaries: tuple[str, ...]
    residual_risks: tuple[str, ...]
    real_backend_evidence: tuple[EvidenceRef, ...] = ()

    def __post_init__(self) -> None:
        _digest(self.candidate_digest, "candidate digest")
        if not self.effect_classes or len(set(self.effect_classes)) != len(self.effect_classes):
            raise QualificationError("effect classes must be a unique nonempty set")
        expected = {(effect, point) for effect in self.effect_classes for point in FailurePoint}
        observed = {(row.effect_class, row.point) for row in self.observations}
        if expected - observed:
            raise QualificationError("failure matrix is incomplete")
        if any(row.candidate_digest != self.candidate_digest for row in self.observations):
            raise QualificationError("failure evidence targets another candidate")
        if any(not row.healthy_path_passed or not row.negative_control_rejected or row.resulting_effect_count > 1 for row in self.observations):
            raise QualificationError("adversarial acceptance failed")
        if not self.attempted_boundaries:
            raise QualificationError("adversarial boundary inventory is required")


@dataclass(frozen=True, slots=True)
class ExternalObligation:
    obligation_id: str
    kind: Disposition
    description: str
    blocks_claims: tuple[str, ...]

    def __post_init__(self) -> None:
        _id(self.obligation_id, "obligation")
        if self.kind not in {Disposition.BLOCKED_CAPABILITY, Disposition.BLOCKED_SOURCE, Disposition.BLOCKED_AUTHORITY}:
            raise QualificationError("obligation must use a blocked disposition")
        if not self.description.strip() or not self.blocks_claims:
            raise QualificationError("obligation requires detail and blocked claims")
        for claim in self.blocks_claims:
            _id(claim, "blocked claim")


@dataclass(frozen=True, slots=True)
class PilotAttempt:
    attempt_id: str
    subject_id: str
    family_id: str
    candidate_digest: str
    status: str
    delivery_receipt: EvidenceRef | None = None

    def __post_init__(self) -> None:
        for name in ("attempt_id", "subject_id", "family_id"):
            _id(getattr(self, name), name)
        _digest(self.candidate_digest, "candidate digest")
        if self.status not in {"accepted", "failed", "blocked", "no_change", "inconclusive"}:
            raise QualificationError("invalid pilot attempt status")
        if self.status == "accepted" and self.delivery_receipt is None:
            raise QualificationError("accepted pilot attempt requires a delivery receipt")


@dataclass(frozen=True, slots=True)
class PilotReport:
    pilot_id: str
    mode: str
    candidate_digest: str
    started_at: int
    ended_at: int
    attempts: tuple[PilotAttempt, ...]
    restart_exercised: bool
    duplicate_effects: int
    avoidable_owner_questions: int
    rollback_evidence: EvidenceRef | None
    obligations: tuple[ExternalObligation, ...] = ()

    def __post_init__(self) -> None:
        _id(self.pilot_id, "pilot")
        if self.mode not in {"self", "external", "roblox"}:
            raise QualificationError("invalid pilot mode")
        _digest(self.candidate_digest, "candidate digest")
        if type(self.started_at) is not int or type(self.ended_at) is not int or self.started_at < 0 or self.ended_at < self.started_at:
            raise QualificationError("pilot timestamps are invalid")
        if type(self.restart_exercised) is not bool:
            raise QualificationError("restart flag must be boolean")
        for value in (self.duplicate_effects, self.avoidable_owner_questions):
            if type(value) is not int or value < 0:
                raise QualificationError("pilot counters must be nonnegative integers")
        if any(row.candidate_digest != self.candidate_digest for row in self.attempts):
            raise QualificationError("pilot attempts target another candidate")

    @property
    def elapsed_seconds(self) -> int:
        return self.ended_at - self.started_at

    def disposition(self) -> Disposition:
        if self.obligations:
            kinds = {item.kind for item in self.obligations}
            if Disposition.BLOCKED_AUTHORITY in kinds:
                return Disposition.BLOCKED_AUTHORITY
            if Disposition.BLOCKED_SOURCE in kinds:
                return Disposition.BLOCKED_SOURCE
            return Disposition.BLOCKED_CAPABILITY
        accepted = [row for row in self.attempts if row.status == "accepted"]
        needed = 3 if self.mode == "self" else 2
        if self.elapsed_seconds < 72 * 60 * 60 or len(accepted) < needed:
            return Disposition.DEFER
        if not self.restart_exercised or self.duplicate_effects or self.avoidable_owner_questions or self.rollback_evidence is None:
            return Disposition.REJECT
        return Disposition.ADOPT


REQUIREMENT_IDS = tuple(f"R{number:02d}" for number in range(1, 19))
NODE_IDS = tuple(f"N{number:02d}" for number in range(34))


@dataclass(frozen=True, slots=True)
class CloseoutManifest:
    release_id: str
    candidate_digest: str
    previous_release_digest: str
    requirement_evidence: Mapping[str, tuple[EvidenceRef, ...]]
    node_dispositions: Mapping[str, Disposition]
    obligations: tuple[ExternalObligation, ...]
    startup_command: tuple[str, ...]
    rollback_command: tuple[str, ...]
    independent_judge_id: str
    sealed_at: int

    def __post_init__(self) -> None:
        _id(self.release_id, "release")
        _digest(self.candidate_digest, "candidate digest")
        _digest(self.previous_release_digest, "previous release digest")
        if set(self.requirement_evidence) != set(REQUIREMENT_IDS):
            raise QualificationError("closeout must map every R01-R18 requirement")
        if set(self.node_dispositions) != set(NODE_IDS):
            raise QualificationError("closeout must disposition every N00-N33 node")
        if any(not isinstance(value, Disposition) for value in self.node_dispositions.values()):
            raise QualificationError("node dispositions must be typed")
        if not self.startup_command or not self.rollback_command or any(not part for part in (*self.startup_command, *self.rollback_command)):
            raise QualificationError("verified startup and rollback commands are required")
        _id(self.independent_judge_id, "judge")
        if type(self.sealed_at) is not int or self.sealed_at < 0:
            raise QualificationError("seal timestamp is invalid")
        if not self.obligations:
            unresolved = [key for key, value in self.node_dispositions.items() if value.name.startswith("BLOCKED")]
            if unresolved:
                raise QualificationError("blocked nodes require explicit obligations")


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    sequence: int
    kind: str
    payload_digest: str
    previous_digest: str | None
    entry_digest: str


class QualificationLedger:
    """Small append-only hash chain for durable qualification references."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def read(self) -> tuple[LedgerEntry, ...]:
        if not self.path.exists():
            return ()
        rows = tuple(LedgerEntry(**json.loads(line)) for line in self.path.read_text(encoding="utf-8").splitlines() if line)
        previous = None
        for index, row in enumerate(rows):
            body = {"sequence": index, "kind": row.kind, "payload_digest": row.payload_digest, "previous_digest": previous}
            expected = canonical_digest(body)
            if row.sequence != index or row.previous_digest != previous or row.entry_digest != expected:
                raise QualificationError("qualification ledger chain is invalid")
            previous = row.entry_digest
        return rows

    def append(self, kind: str, payload: object) -> LedgerEntry:
        _id(kind, "entry kind")
        rows = self.read()
        body = {
            "sequence": len(rows),
            "kind": kind,
            "payload_digest": canonical_digest(payload),
            "previous_digest": rows[-1].entry_digest if rows else None,
        }
        entry = LedgerEntry(**body, entry_digest=canonical_digest(body))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(asdict(entry), sort_keys=True, separators=(",", ":")) + "\n")
            stream.flush()
        return entry


def unresolved_claims(obligations: Iterable[ExternalObligation]) -> frozenset[str]:
    return frozenset(claim for obligation in obligations for claim in obligation.blocks_claims)
