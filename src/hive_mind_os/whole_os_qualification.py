"""Typed N28/N29/N31/N32/N33 qualification and closeout contracts.

The objects in this module record observations; they do not manufacture external
authority, runtime access, delivery receipts, elapsed pilot time, or a promotion.
Host integrations remain responsible for authenticating evidence references.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Iterable, Mapping


class QualificationError(ValueError):
    """A closed qualification contract was violated."""


def canonical_digest(value: object) -> str:
    return (
        "sha256:"
        + sha256(
            json.dumps(
                value, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
        ).hexdigest()
    )


def _id(value: object, name: str) -> None:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or any(c.isspace() for c in value)
    ):
        raise QualificationError(f"{name} must be an exact nonempty identifier")


def _digest(value: object, name: str) -> None:
    if (
        type(value) is not str
        or len(value) != 71
        or not value.startswith("sha256:")
        or set(value[7:]) - set("0123456789abcdef")
    ):
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


class QualificationClaimScope(StrEnum):
    """The exact claim a pilot or release receipt is allowed to support."""

    BOUNDED_OPERATIONAL_PRODUCTION = "bounded-operational-production-pilot"
    FULL_AUTONOMY_OR_SUPERIORITY = "full-autonomy-or-superiority"


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
        if (
            type(self.kind) is not EvidenceKind
            or type(self.observed_at) is not int
            or self.observed_at < 0
        ):
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
        if (
            type(self.runtime_supported) is not bool
            or type(self.compile_supported) is not bool
        ):
            raise QualificationError("capability flags must be exact booleans")
        if not self.runtime_supported and not self.compile_supported:
            if (
                type(self.incomplete_reason) is not str
                or not self.incomplete_reason.strip()
            ):
                raise QualificationError("unsupported capability requires a reason")
        elif self.incomplete_reason is not None:
            raise QualificationError(
                "supported capability cannot carry an incomplete reason"
            )
        if len(set(self.evidence)) != len(self.evidence):
            raise QualificationError("capability evidence must be unique")


REQUIRED_PROFILES = frozenset(
    {"self-python", "external-python", "node-typescript", "go", "rust", "roblox"}
)


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
            raise QualificationError(
                "composition must declare each required profile exactly once"
            )
        if not self.component_digests:
            raise QualificationError("composition requires exact component digests")
        for name, digest in self.component_digests.items():
            _id(name, "component name")
            _digest(digest, "component digest")
        if self.legacy_plan_policy not in {
            "refuse-ambiguous",
            "migrate-explicit-subject",
            "inert-only",
        }:
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
        if (
            type(self.healthy_path_passed) is not bool
            or type(self.negative_control_rejected) is not bool
        ):
            raise QualificationError("failure observation flags must be booleans")
        if (
            type(self.resulting_effect_count) is not int
            or self.resulting_effect_count < 0
        ):
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
        if not self.effect_classes or len(set(self.effect_classes)) != len(
            self.effect_classes
        ):
            raise QualificationError("effect classes must be a unique nonempty set")
        expected = {
            (effect, point) for effect in self.effect_classes for point in FailurePoint
        }
        observed = {(row.effect_class, row.point) for row in self.observations}
        if expected - observed:
            raise QualificationError("failure matrix is incomplete")
        if any(
            row.candidate_digest != self.candidate_digest for row in self.observations
        ):
            raise QualificationError("failure evidence targets another candidate")
        if any(
            not row.healthy_path_passed
            or not row.negative_control_rejected
            or row.resulting_effect_count > 1
            for row in self.observations
        ):
            raise QualificationError("adversarial acceptance failed")
        if not self.attempted_boundaries or len(set(self.attempted_boundaries)) != len(
            self.attempted_boundaries
        ):
            raise QualificationError(
                "adversarial boundary inventory is required and unique"
            )


@dataclass(frozen=True, slots=True)
class ExternalObligation:
    obligation_id: str
    kind: Disposition
    description: str
    blocks_claims: tuple[str, ...]

    def __post_init__(self) -> None:
        _id(self.obligation_id, "obligation")
        if self.kind not in {
            Disposition.BLOCKED_CAPABILITY,
            Disposition.BLOCKED_SOURCE,
            Disposition.BLOCKED_AUTHORITY,
        }:
            raise QualificationError("obligation must use a blocked disposition")
        if not self.description.strip() or not self.blocks_claims:
            raise QualificationError("obligation requires detail and blocked claims")
        for claim in self.blocks_claims:
            _id(claim, "blocked claim")


@dataclass(frozen=True, slots=True)
class PilotRuntimeEvidence:
    check_class: str
    receipt: EvidenceRef

    def __post_init__(self) -> None:
        _id(self.check_class, "runtime check class")


REQUIRED_ROBLOX_RUNTIME_CHECKS = frozenset(
    {
        "core-loop",
        "multiplayer",
        "exploit-abuse",
        "persistence-rejoin",
        "network-degradation",
        "asset-provenance",
        "target-device-performance",
    }
)


@dataclass(frozen=True, slots=True)
class PilotAttempt:
    attempt_id: str
    subject_id: str
    family_id: str
    candidate_digest: str
    status: str
    delivery_receipt: EvidenceRef | None = None
    started_at: int | None = None
    ended_at: int | None = None
    resource_units: int = 1
    domain: str | None = None
    runtime_evidence: tuple[PilotRuntimeEvidence, ...] = ()
    target_runs_without_hive: bool | None = None

    def __post_init__(self) -> None:
        for name in ("attempt_id", "subject_id", "family_id"):
            _id(getattr(self, name), name)
        _digest(self.candidate_digest, "candidate digest")
        if self.status not in {
            "accepted",
            "failed",
            "blocked",
            "no_change",
            "inconclusive",
        }:
            raise QualificationError("invalid pilot attempt status")
        if self.status == "accepted" and self.delivery_receipt is None:
            raise QualificationError(
                "accepted pilot attempt requires a delivery receipt"
            )
        if self.status == "accepted" and (
            self.delivery_receipt is None
            or self.delivery_receipt.kind is not EvidenceKind.EXTERNAL_RECEIPT
        ):
            raise QualificationError(
                "accepted pilot attempt requires an external delivery receipt"
            )
        if (self.started_at is None) != (self.ended_at is None):
            raise QualificationError("pilot attempt timestamps must be paired")
        if self.started_at is not None and (
            type(self.started_at) is not int
            or type(self.ended_at) is not int
            or self.started_at < 0
            or self.ended_at < self.started_at
        ):
            raise QualificationError("pilot attempt timestamps are invalid")
        if type(self.resource_units) is not int or self.resource_units < 1:
            raise QualificationError("pilot resource units must be a positive integer")
        if self.domain is not None:
            _id(self.domain, "pilot domain")
        if len(set(self.runtime_evidence)) != len(self.runtime_evidence):
            raise QualificationError("pilot runtime evidence must be unique")
        if self.target_runs_without_hive is not None and (
            type(self.target_runs_without_hive) is not bool
        ):
            raise QualificationError("target runtime independence must be boolean")
        for evidence in self.runtime_evidence:
            if evidence.receipt.subject_id != self.subject_id:
                raise QualificationError("runtime evidence targets another subject")
        if self.delivery_receipt is not None and (
            self.delivery_receipt.subject_id != self.subject_id
        ):
            raise QualificationError("delivery receipt targets another subject")


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
    active_attempt_ids: tuple[str, ...] = ()
    restart_evidence: EvidenceRef | None = None
    observation_evidence: EvidenceRef | None = None
    subject_ids: tuple[str, ...] = ()
    claim_scope: QualificationClaimScope = (
        QualificationClaimScope.FULL_AUTONOMY_OR_SUPERIORITY
    )
    production_candidate: EvidenceRef | None = None
    benchmark_candidate: EvidenceRef | None = None

    def __post_init__(self) -> None:
        _id(self.pilot_id, "pilot")
        if self.mode not in {"self", "external", "roblox"}:
            raise QualificationError("invalid pilot mode")
        if type(self.claim_scope) is not QualificationClaimScope:
            raise QualificationError("pilot claim scope must be typed")
        _digest(self.candidate_digest, "candidate digest")
        if len(self.subject_ids) != len(set(self.subject_ids)):
            raise QualificationError("pilot subject identities must be unique")
        for subject_id in self.subject_ids:
            _id(subject_id, "pilot subject")
        if (
            type(self.started_at) is not int
            or type(self.ended_at) is not int
            or self.started_at < 0
            or self.ended_at < self.started_at
        ):
            raise QualificationError("pilot timestamps are invalid")
        if type(self.restart_exercised) is not bool:
            raise QualificationError("restart flag must be boolean")
        for value in (self.duplicate_effects, self.avoidable_owner_questions):
            if type(value) is not int or value < 0:
                raise QualificationError("pilot counters must be nonnegative integers")
        if any(row.candidate_digest != self.candidate_digest for row in self.attempts):
            raise QualificationError("pilot attempts target another candidate")
        if self.subject_ids and any(
            row.subject_id not in self.subject_ids for row in self.attempts
        ):
            raise QualificationError("pilot attempt targets an undeclared subject")
        attempt_ids = tuple(row.attempt_id for row in self.attempts)
        if len(attempt_ids) != len(set(attempt_ids)):
            raise QualificationError("pilot attempt identities must be unique")
        accepted_receipts = tuple(
            row.delivery_receipt
            for row in self.attempts
            if row.status == "accepted"
        )
        if len(accepted_receipts) != len(set(accepted_receipts)):
            raise QualificationError("accepted delivery receipts must be unique")
        if len(self.active_attempt_ids) != len(set(self.active_attempt_ids)):
            raise QualificationError("active pilot attempt identities must be unique")
        for attempt_id in self.active_attempt_ids:
            _id(attempt_id, "active pilot attempt")
        for evidence in (self.restart_evidence, self.observation_evidence):
            if evidence is not None and evidence.subject_id != self.pilot_id:
                raise QualificationError("pilot control evidence targets another pilot")
        for evidence in (self.production_candidate, self.benchmark_candidate):
            if evidence is not None and evidence.subject_id != self.candidate_digest:
                raise QualificationError("pilot candidate evidence targets another candidate")

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
        if self.active_attempt_ids:
            return Disposition.DEFER
        if not self.subject_ids or self.production_candidate is None or (
            self.production_candidate.kind
            not in {EvidenceKind.ATTESTED_REAL, EvidenceKind.EXTERNAL_RECEIPT}
        ):
            return Disposition.DEFER
        if self.claim_scope is QualificationClaimScope.FULL_AUTONOMY_OR_SUPERIORITY and (
            self.benchmark_candidate is None
            or self.benchmark_candidate.kind
            not in {EvidenceKind.ATTESTED_REAL, EvidenceKind.EXTERNAL_RECEIPT}
        ):
            return Disposition.DEFER
        accepted = [row for row in self.attempts if row.status == "accepted"]
        needed = {
            "self": 3,
            "external": max(2, len(self.subject_ids)),
            "roblox": 1,
        }[self.mode]
        accepted_families = {row.family_id for row in accepted}
        if (
            self.elapsed_seconds < 72 * 60 * 60
            or len(accepted) < needed
            or len(accepted_families) < needed
            or any(
                row.started_at is None
                or row.ended_at is None
                or row.started_at < self.started_at
                or row.ended_at > self.ended_at
                for row in accepted
            )
        ):
            return Disposition.DEFER
        if self.mode == "external":
            subjects = {row.subject_id for row in accepted}
            roblox = [row for row in accepted if row.domain == "roblox"]
            if (
                len(self.subject_ids) < 2
                or not set(self.subject_ids).issubset(subjects)
                or any(row.domain is None for row in accepted)
                or any(row.target_runs_without_hive is not True for row in accepted)
                or any(not _roblox_runtime_complete(row) for row in roblox)
            ):
                return Disposition.DEFER
        if self.mode == "roblox" and any(
            row.domain != "roblox" or not _roblox_runtime_complete(row)
            for row in accepted
        ):
            return Disposition.DEFER
        if (
            self.restart_evidence is None
            or self.restart_evidence.kind
            not in {EvidenceKind.ATTESTED_REAL, EvidenceKind.EXTERNAL_RECEIPT}
            or self.observation_evidence is None
            or self.observation_evidence.kind
            not in {EvidenceKind.ATTESTED_REAL, EvidenceKind.EXTERNAL_RECEIPT}
            or self.observation_evidence.observed_at < self.ended_at
            or self.rollback_evidence is None
            or self.rollback_evidence.kind
            not in {EvidenceKind.ATTESTED_REAL, EvidenceKind.EXTERNAL_RECEIPT}
        ):
            return Disposition.DEFER
        if (
            not self.restart_exercised
            or self.duplicate_effects
            or self.avoidable_owner_questions
        ):
            return Disposition.REJECT
        return Disposition.ADOPT


def _roblox_runtime_complete(attempt: PilotAttempt) -> bool:
    checks = {item.check_class for item in attempt.runtime_evidence}
    return checks == REQUIRED_ROBLOX_RUNTIME_CHECKS and all(
        item.receipt.kind
        in {EvidenceKind.ATTESTED_REAL, EvidenceKind.EXTERNAL_RECEIPT}
        for item in attempt.runtime_evidence
    )


REQUIREMENT_IDS = tuple(f"R{number:02d}" for number in range(1, 19))
NODE_IDS = tuple(f"N{number:02d}" for number in range(34))
SPECIALIST_ROLE_IDS = frozenset(
    {
        "orchestrator",
        "explorer",
        "architect",
        "builder",
        "curator",
        "integrator",
        "steward",
        "optimizer",
    }
)
LIFECYCLE_STAGE_IDS = frozenset(
    {"discover", "design", "build", "validate", "grow", "maintain", "integrate"}
)


@dataclass(frozen=True, slots=True)
class CloseoutAssessment:
    """Evidence-bearing disposition for one requirement or campaign node."""

    subject_id: str
    disposition: Disposition
    evidence: tuple[EvidenceRef, ...] = ()
    obligation_ids: tuple[str, ...] = ()
    rationale: str = ""

    def __post_init__(self) -> None:
        _id(self.subject_id, "closeout subject")
        if type(self.disposition) is not Disposition:
            raise QualificationError("closeout disposition must be typed")
        if len(set(self.evidence)) != len(self.evidence):
            raise QualificationError("closeout evidence must be unique")
        if len(set(self.obligation_ids)) != len(self.obligation_ids):
            raise QualificationError("closeout obligations must be unique")
        for obligation_id in self.obligation_ids:
            _id(obligation_id, "closeout obligation")
        blocked = self.disposition.name.startswith("BLOCKED")
        if self.disposition in {Disposition.ADOPT, Disposition.ADAPT} and not self.evidence:
            raise QualificationError("adopted or adapted closeout requires evidence")
        if blocked and not self.obligation_ids:
            raise QualificationError("blocked closeout requires an explicit obligation")
        if not blocked and self.obligation_ids:
            raise QualificationError("only blocked closeout may reference obligations")
        if self.disposition not in {Disposition.ADOPT, Disposition.ADAPT}:
            if type(self.rationale) is not str or not self.rationale.strip():
                raise QualificationError("unresolved closeout requires a rationale")


@dataclass(frozen=True, slots=True)
class OperationalReceipt:
    """Attested successful execution of an operator command on exact candidate bytes."""

    argv: tuple[str, ...]
    candidate_digest: str
    exit_code: int
    evidence: EvidenceRef

    def __post_init__(self) -> None:
        if not self.argv or any(
            type(part) is not str or not part or "\x00" in part for part in self.argv
        ):
            raise QualificationError("operational command must be direct arguments")
        _digest(self.candidate_digest, "operational candidate digest")
        if type(self.exit_code) is not int or self.exit_code != 0:
            raise QualificationError("operational receipt must record a successful exit")
        if self.evidence.kind is EvidenceKind.SYNTHETIC:
            raise QualificationError("operational receipt must be attested real evidence")
        if self.evidence.subject_id != self.candidate_digest:
            raise QualificationError("operational receipt targets another candidate")


@dataclass(frozen=True, slots=True)
class CloseoutManifest:
    release_id: str
    candidate_digest: str
    previous_release_digest: str
    requirement_assessments: Mapping[str, CloseoutAssessment]
    node_assessments: Mapping[str, CloseoutAssessment]
    obligations: tuple[ExternalObligation, ...]
    role_evidence: Mapping[str, tuple[EvidenceRef, ...]]
    lifecycle_evidence: Mapping[str, tuple[EvidenceRef, ...]]
    startup_receipt: OperationalReceipt
    rollback_receipt: OperationalReceipt
    builder_id: str
    independent_judge_id: str
    final_disposition: Disposition
    final_rationale: str
    sealed_at: int
    claim_scope: QualificationClaimScope = (
        QualificationClaimScope.FULL_AUTONOMY_OR_SUPERIORITY
    )

    def __post_init__(self) -> None:
        _id(self.release_id, "release")
        _digest(self.candidate_digest, "candidate digest")
        _digest(self.previous_release_digest, "previous release digest")
        if set(self.requirement_assessments) != set(REQUIREMENT_IDS):
            raise QualificationError("closeout must map every R01-R18 requirement")
        if any(
            key != assessment.subject_id
            for key, assessment in self.requirement_assessments.items()
        ):
            raise QualificationError("requirement closeout keys must match subjects")
        if set(self.node_assessments) != set(NODE_IDS):
            raise QualificationError("closeout must disposition every N00-N33 node")
        if any(
            key != assessment.subject_id
            for key, assessment in self.node_assessments.items()
        ):
            raise QualificationError("node closeout keys must match subjects")
        obligation_by_id = {item.obligation_id: item for item in self.obligations}
        if len(obligation_by_id) != len(self.obligations):
            raise QualificationError("closeout obligation identities must be unique")
        for assessment in (
            *self.requirement_assessments.values(),
            *self.node_assessments.values(),
        ):
            for obligation_id in assessment.obligation_ids:
                obligation = obligation_by_id.get(obligation_id)
                if obligation is None:
                    raise QualificationError("closeout references an unknown obligation")
                if obligation.kind is not assessment.disposition:
                    raise QualificationError("closeout obligation kind does not match")
                if assessment.subject_id not in obligation.blocks_claims:
                    raise QualificationError("obligation does not block its closeout subject")
        if set(self.role_evidence) != SPECIALIST_ROLE_IDS:
            raise QualificationError("closeout must evidence all eight specialist roles")
        if set(self.lifecycle_evidence) != LIFECYCLE_STAGE_IDS:
            raise QualificationError("closeout must evidence every lifecycle stage")
        for values in (*self.role_evidence.values(), *self.lifecycle_evidence.values()):
            if not values or any(item.kind is EvidenceKind.SYNTHETIC for item in values):
                raise QualificationError("role and lifecycle evidence must be attested")
            if len(set(values)) != len(values):
                raise QualificationError("role and lifecycle evidence must be unique")
        if self.startup_receipt.candidate_digest != self.candidate_digest:
            raise QualificationError("startup receipt targets another candidate")
        if self.rollback_receipt.candidate_digest != self.candidate_digest:
            raise QualificationError("rollback receipt targets another candidate")
        _id(self.builder_id, "builder")
        _id(self.independent_judge_id, "judge")
        if self.builder_id == self.independent_judge_id:
            raise QualificationError("closeout judge must be independent of the builder")
        if type(self.final_disposition) is not Disposition:
            raise QualificationError("final release disposition must be typed")
        if type(self.claim_scope) is not QualificationClaimScope:
            raise QualificationError("release claim scope must be typed")
        if type(self.final_rationale) is not str or not self.final_rationale.strip():
            raise QualificationError("final release disposition requires a rationale")
        if self.final_disposition in {Disposition.ADOPT, Disposition.ADAPT}:
            required_nodes = (
                ("N28", "N29", "N32", "N33")
                if self.claim_scope
                is QualificationClaimScope.BOUNDED_OPERATIONAL_PRODUCTION
                else ("N30", "N31", "N32", "N33")
            )
            for node_id in required_nodes:
                if self.node_assessments[node_id].disposition not in {
                    Disposition.ADOPT,
                    Disposition.ADAPT,
                }:
                    raise QualificationError(
                        "positive release lacks required claim-scoped tournament or pilot closeout"
                    )
        if type(self.sealed_at) is not int or self.sealed_at < 0:
            raise QualificationError("seal timestamp is invalid")


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
        rows = tuple(
            LedgerEntry(**json.loads(line))
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line
        )
        previous = None
        for index, row in enumerate(rows):
            body = {
                "sequence": index,
                "kind": row.kind,
                "payload_digest": row.payload_digest,
                "previous_digest": previous,
            }
            expected = canonical_digest(body)
            if (
                row.sequence != index
                or row.previous_digest != previous
                or row.entry_digest != expected
            ):
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
            stream.write(
                json.dumps(asdict(entry), sort_keys=True, separators=(",", ":")) + "\n"
            )
            stream.flush()
        return entry


def unresolved_claims(obligations: Iterable[ExternalObligation]) -> frozenset[str]:
    return frozenset(
        claim for obligation in obligations for claim in obligation.blocks_claims
    )
