"""Bounded two-generation feedback loop for prompt challengers.

The runtime composes the existing challenger generator, held-out evaluator,
recursive qualification contracts, prompt registry, courtroom, and promotion
authority.  It deliberately has no champion-mutation method.  Court-backed
decisions are submitted to :class:`PromotionAuthority`, but applying such a
decision remains an explicit call on that pre-existing authority by a caller.

The lifecycle is strict and append-only::

    finding -> owned hypothesis -> sealed plan -> materialized prompt
            -> externally bound evaluation -> court decision
            -> generation-2 re-entry (RETEST/DEFER only)

Every terminal and losing outcome is retained under the run root.  The source
checkout and champion pointer are sampled around each operation that can write
run-local state.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Any

from ..models import Role, utc_now
from ..prompt_registry import PromptRegistry, prompt_digest
from ..recursive_improvement import ExperimentVerdict
from .artifacts import ArtifactStore
from .canonical import canonical_bytes, canonical_digest
from .challengers import (
    AcceptedLesson,
    ChallengerGenerator,
    ChallengerSpec,
)
from .court_runtime import CourtDisposition, CourtHistory
from .evaluation_authority import (
    BoundSurfaceEvidence,
    CandidateAuthorityBinding,
    EvaluationAuthorityError,
    EvaluationAuthorityManifest,
    RepositoryBinding,
    capture_repository_binding,
    load_evaluation_authority_manifest,
    sealed_holdout_commitment,
    validate_surface_set,
)
from .evaluation_runtime import (
    ChallengerDescriptor,
    EvaluationIdentities,
    EvaluationRecord,
    EvaluationRuntime,
    EvaluationVerdict,
    HoldoutSeal,
    SealedHoldout,
    SurfaceKind,
)
from .promotion import (
    PromotionAuthority,
    PromotionCandidate,
    PromotionDecision,
)
from .qualification import (
    EvidenceReceipt,
    IssuerAuthority,
    QualificationDecision,
    QualificationDisposition,
    QualificationLevel,
    QualificationPolicy,
    QualificationRequest,
    qualify_claim,
)

__all__ = [
    "AuthorityEvaluationOutcome",
    "ChallengerAppeal",
    "ChallengerFinding",
    "ChallengerProposal",
    "ChallengerRuntimeError",
    "EvaluationPlanSeal",
    "KeepPromotionUnsupportedError",
    "MaterializedChallenger",
    "OwnedHypothesis",
    "PlannedSurface",
    "V2PromotionDisposition",
    "V2ChallengerRuntime",
]


class ChallengerRuntimeError(RuntimeError):
    """The challenger lifecycle, budget, or immutability boundary was violated."""


class V2PromotionDisposition(StrEnum):
    COURT_ELIGIBLE = "court-eligible"
    DEFER_UNSUPPORTED = "defer-unsupported"


class KeepPromotionUnsupportedError(ChallengerRuntimeError):
    """V2 deliberately retains KEEP but cannot authorize its promotion."""

    disposition = V2PromotionDisposition.DEFER_UNSUPPORTED


def _text(value: object, label: str) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise ChallengerRuntimeError(
            f"{label} must be an exact non-empty trimmed string"
        )
    return value


def _digest(value: object, label: str) -> str:
    text = _text(value, label)
    if not text.startswith("sha256:") or len(text) != 71:
        raise ChallengerRuntimeError(f"{label} must be a canonical sha256 digest")
    if any(character not in "0123456789abcdef" for character in text[7:]):
        raise ChallengerRuntimeError(f"{label} must be a canonical sha256 digest")
    return text


def _moment(value: object, label: str) -> datetime:
    text = _text(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ChallengerRuntimeError(
            f"{label} must be an RFC 3339 timestamp"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ChallengerRuntimeError(f"{label} must include an offset")
    return parsed.astimezone(timezone.utc)


def _refs(values: Iterable[str], label: str) -> tuple[str, ...]:
    items = tuple(values)
    if not items or any(
        type(item) is not str or not item.strip() or item != item.strip()
        for item in items
    ):
        raise ChallengerRuntimeError(f"{label} require retained references")
    if len(set(items)) != len(items):
        raise ChallengerRuntimeError(f"{label} must be unique")
    return items


def _file_reference(path: Path) -> str:
    return f"{path.as_posix()}#sha256:{sha256(path.read_bytes()).hexdigest()}"


@dataclass(frozen=True, slots=True, kw_only=True)
class ChallengerFinding:
    """An evidence-backed problem statement owned by the authorized proposer."""

    finding_id: str
    role: str
    source_episode_id: str
    summary: str
    error_class: str
    proposed_change: str
    falsifier: str
    evidence_refs: tuple[str, ...]
    owner_id: str
    expires_at: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.finding_id, "finding_id"),
            (self.source_episode_id, "source_episode_id"),
            (self.summary, "finding summary"),
            (self.error_class, "error_class"),
            (self.proposed_change, "proposed_change"),
            (self.falsifier, "falsifier"),
            (self.owner_id, "finding owner"),
        ):
            _text(value, label)
        try:
            object.__setattr__(self, "role", Role(self.role).value)
        except ValueError as error:
            raise ChallengerRuntimeError("finding role is not a kernel role") from error
        object.__setattr__(
            self, "evidence_refs", _refs(self.evidence_refs, "finding evidence")
        )
        _moment(self.expires_at, "finding expires_at")


@dataclass(frozen=True, slots=True, kw_only=True)
class OwnedHypothesis:
    """A concrete claim with an explicit observation that would falsify it."""

    hypothesis_id: str
    finding_id: str
    role: str
    owner_id: str
    statement: str
    falsifier: str
    parent_champion_digest: str
    evidence_refs: tuple[str, ...]
    generation: int
    prior_outcome_digest: str | None = None

    def __post_init__(self) -> None:
        for value, label in (
            (self.hypothesis_id, "hypothesis_id"),
            (self.finding_id, "hypothesis finding_id"),
            (self.owner_id, "hypothesis owner"),
            (self.statement, "hypothesis statement"),
            (self.falsifier, "hypothesis falsifier"),
        ):
            _text(value, label)
        try:
            object.__setattr__(self, "role", Role(self.role).value)
        except ValueError as error:
            raise ChallengerRuntimeError(
                "hypothesis role is not a kernel role"
            ) from error
        _digest(self.parent_champion_digest, "hypothesis parent champion")
        object.__setattr__(
            self,
            "evidence_refs",
            _refs(self.evidence_refs, "hypothesis evidence"),
        )
        if type(self.generation) is not int or self.generation not in {1, 2}:
            raise ChallengerRuntimeError("hypothesis generation must be 1 or 2")
        if self.generation == 1 and self.prior_outcome_digest is not None:
            raise ChallengerRuntimeError(
                "generation-1 hypothesis cannot cite a prior outcome"
            )
        if self.generation == 2:
            _digest(self.prior_outcome_digest, "generation-2 prior outcome")


@dataclass(frozen=True, slots=True, kw_only=True)
class ChallengerProposal:
    hypothesis: OwnedHypothesis
    lesson: AcceptedLesson
    proposal_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.hypothesis, OwnedHypothesis):
            raise ChallengerRuntimeError("proposal requires an OwnedHypothesis")
        if not isinstance(self.lesson, AcceptedLesson):
            raise ChallengerRuntimeError("proposal requires an AcceptedLesson")
        _digest(self.proposal_digest, "proposal digest")
        if self.proposal_digest != canonical_digest(
            {"hypothesis": self.hypothesis, "lesson": self.lesson}
        ):
            raise ChallengerRuntimeError("proposal digest mismatch")


@dataclass(frozen=True, slots=True, kw_only=True)
class PlannedSurface:
    kind: SurfaceKind
    name: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, SurfaceKind):
            raise ChallengerRuntimeError("planned surface kind is invalid")
        _text(self.name, "planned surface name")


@dataclass(frozen=True, slots=True, kw_only=True)
class EvaluationPlanSeal:
    plan_id: str
    plan_digest: str
    proposal_digest: str
    hypothesis_id: str
    generation: int
    prior_outcome_digest: str | None
    surfaces: tuple[PlannedSurface, ...]
    holdout_id: str
    holdout_seal: HoldoutSeal
    record_path: Path

    def __post_init__(self) -> None:
        for value, label in (
            (self.plan_id, "plan_id"),
            (self.hypothesis_id, "plan hypothesis_id"),
            (self.holdout_id, "plan holdout_id"),
        ):
            _text(value, label)
        for value, label in (
            (self.plan_digest, "plan digest"),
            (self.proposal_digest, "plan proposal digest"),
        ):
            _digest(value, label)
        if type(self.generation) is not int or self.generation not in {1, 2}:
            raise ChallengerRuntimeError("plan generation must be 1 or 2")
        if self.generation == 2:
            _digest(self.prior_outcome_digest, "plan prior outcome")
        if not self.surfaces or any(
            not isinstance(item, PlannedSurface) for item in self.surfaces
        ):
            raise ChallengerRuntimeError("plan requires PlannedSurface values")
        if not isinstance(self.holdout_seal, HoldoutSeal):
            raise ChallengerRuntimeError("plan requires a HoldoutSeal")
        if not isinstance(self.record_path, Path) or not self.record_path.is_absolute():
            raise ChallengerRuntimeError("plan record path must be absolute")


@dataclass(frozen=True, slots=True, kw_only=True)
class MaterializedChallenger:
    proposal: ChallengerProposal
    plan_digest: str
    spec: ChallengerSpec
    descriptor: ChallengerDescriptor
    binding: CandidateAuthorityBinding
    experiment_id: str
    materialization_digest: str
    record_path: Path

    def __post_init__(self) -> None:
        if not isinstance(self.proposal, ChallengerProposal):
            raise ChallengerRuntimeError("materialization requires a proposal")
        if not isinstance(self.spec, ChallengerSpec):
            raise ChallengerRuntimeError("materialization requires a ChallengerSpec")
        if not isinstance(self.descriptor, ChallengerDescriptor):
            raise ChallengerRuntimeError("materialization requires a descriptor")
        if not isinstance(self.binding, CandidateAuthorityBinding):
            raise ChallengerRuntimeError("materialization requires a candidate binding")
        _digest(self.plan_digest, "materialization plan digest")
        _text(self.experiment_id, "materialization experiment id")
        _digest(self.materialization_digest, "materialization digest")


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthorityEvaluationOutcome:
    materialized: MaterializedChallenger
    plan_digest: str
    verdict: EvaluationVerdict
    reasons: tuple[str, ...]
    qualification: QualificationDecision | None
    evaluation_record: EvaluationRecord | None
    surface_receipts: tuple[tuple[str, str], ...]
    qualification_receipts: tuple[tuple[str, str], ...]
    prior_outcome_digest: str | None
    outcome_digest: str
    record_path: Path

    def __post_init__(self) -> None:
        if not isinstance(self.materialized, MaterializedChallenger):
            raise ChallengerRuntimeError("outcome requires a materialized challenger")
        _digest(self.plan_digest, "outcome plan digest")
        if not isinstance(self.verdict, EvaluationVerdict):
            raise ChallengerRuntimeError("outcome verdict is invalid")
        object.__setattr__(self, "reasons", _refs(self.reasons, "outcome reasons"))
        _digest(self.outcome_digest, "outcome digest")

    @property
    def surface_receipt_ids(self) -> tuple[str, ...]:
        return tuple(receipt_id for receipt_id, _ in self.surface_receipts)

    @property
    def surface_artifact_digests(self) -> tuple[str, ...]:
        return tuple(digest for _, digest in self.surface_receipts)

    @property
    def qualification_artifact_digests(self) -> tuple[str, ...]:
        return tuple(digest for _, digest in self.qualification_receipts)

    @property
    def promotion_disposition(self) -> V2PromotionDisposition:
        if self.verdict is EvaluationVerdict.KEEP:
            return V2PromotionDisposition.DEFER_UNSUPPORTED
        return V2PromotionDisposition.COURT_ELIGIBLE


@dataclass(frozen=True, slots=True, kw_only=True)
class ChallengerAppeal:
    appeal_id: str
    outcome_digest: str
    decision: PromotionDecision
    court_disposition: CourtDisposition
    appeal_digest: str
    record_path: Path

    def __post_init__(self) -> None:
        _text(self.appeal_id, "appeal_id")
        _digest(self.outcome_digest, "appeal outcome digest")
        if not isinstance(self.decision, PromotionDecision):
            raise ChallengerRuntimeError("appeal requires a PromotionDecision")
        if not isinstance(self.court_disposition, CourtDisposition):
            raise ChallengerRuntimeError("appeal court disposition is invalid")
        _digest(self.appeal_digest, "appeal digest")


class V2ChallengerRuntime:
    """Two-generation offline evaluator with no champion-mutation surface."""

    def __init__(
        self,
        *,
        manifest: EvaluationAuthorityManifest,
        repository_root: str | Path,
        run_root: str | Path,
        registry: PromptRegistry,
        artifact_store: ArtifactStore,
        promotion_authority: PromotionAuthority,
        evaluation_runtime: EvaluationRuntime | None = None,
        now: Callable[[], str] = utc_now,
    ) -> None:
        if not isinstance(manifest, EvaluationAuthorityManifest):
            raise ChallengerRuntimeError(
                "runtime requires an EvaluationAuthorityManifest"
            )
        if not isinstance(registry, PromptRegistry):
            raise ChallengerRuntimeError("runtime requires a PromptRegistry")
        if not isinstance(artifact_store, ArtifactStore):
            raise ChallengerRuntimeError("runtime requires an ArtifactStore")
        if not isinstance(promotion_authority, PromotionAuthority):
            raise ChallengerRuntimeError("runtime requires a PromotionAuthority")
        if promotion_authority.registry is not registry:
            raise ChallengerRuntimeError(
                "promotion authority and runtime must share one prompt registry"
            )
        if evaluation_runtime is not None and not isinstance(
            evaluation_runtime, EvaluationRuntime
        ):
            raise ChallengerRuntimeError(
                "evaluation_runtime must be an EvaluationRuntime"
            )
        self.repository_root = self._absolute_directory(
            repository_root, "repository root"
        )
        self.run_root = self._absolute_directory(run_root, "run root", create=True)
        if self.run_root == self.repository_root or self.run_root.is_relative_to(
            self.repository_root
        ):
            raise ChallengerRuntimeError("run root must be outside the source checkout")
        if not registry.root.is_relative_to(self.run_root):
            raise ChallengerRuntimeError("prompt registry must be inside the run root")
        if not artifact_store.root.resolve().is_relative_to(self.run_root):
            raise ChallengerRuntimeError("artifact store must be inside the run root")
        started_raw = now()
        try:
            authenticated = load_evaluation_authority_manifest(
                manifest.source_path,
                expected_digest=manifest.manifest_digest,
                repository_root=self.repository_root,
                candidate_root=registry.root,
                run_root=self.run_root,
                as_of=started_raw,
            )
        except EvaluationAuthorityError as error:
            raise ChallengerRuntimeError(
                "runtime could not re-authenticate the external authority"
            ) from error
        if authenticated != manifest:
            raise ChallengerRuntimeError(
                "runtime authority differs from the authenticated document"
            )
        self.manifest = authenticated
        self.registry = registry
        self.artifact_store = artifact_store
        self.promotion_authority = promotion_authority
        self.evaluation_runtime = evaluation_runtime or EvaluationRuntime()
        if (
            self.evaluation_runtime.contract.fingerprint
            != manifest.contract_fingerprint
        ):
            raise ChallengerRuntimeError(
                "evaluation runtime contract does not match the authority"
            )
        self._now = now
        self._started_at = _moment(started_raw, "runtime start")
        self._generator = ChallengerGenerator(
            generated_by=manifest.identities.proposer_id,
            registry=registry,
            now=now,
        )
        self._proposals: dict[str, ChallengerProposal] = {}
        self._plans: dict[str, EvaluationPlanSeal] = {}
        self._materialized: dict[str, MaterializedChallenger] = {}
        self._outcomes: dict[str, AuthorityEvaluationOutcome] = {}
        self._appeals: dict[str, ChallengerAppeal] = {}
        self._reentered_outcomes: set[str] = set()
        self._evidence_root = self.run_root / "challenger-authority"
        self._evidence_root.mkdir(parents=True, exist_ok=True)

        snapshot = capture_repository_binding(self.repository_root)
        self._validate_repository_manifest(snapshot)
        for role in Role:
            current = self.registry.champion_digest(role)
            if current != manifest.champion_digest(role):
                raise ChallengerRuntimeError(
                    f"registry champion does not match authority for {role.value}"
                )

    @staticmethod
    def _absolute_directory(
        value: str | Path, label: str, *, create: bool = False
    ) -> Path:
        path = Path(value)
        if not path.is_absolute():
            raise ChallengerRuntimeError(f"{label} must be absolute")
        if create:
            path.mkdir(parents=True, exist_ok=True)
        try:
            resolved = path.resolve(strict=True)
        except OSError as error:
            raise ChallengerRuntimeError(f"{label} is unavailable") from error
        if not resolved.is_dir():
            raise ChallengerRuntimeError(f"{label} must be a directory")
        return resolved

    def _check_budget_clock(self) -> str:
        raw = self._now()
        current = _moment(raw, "runtime current time")
        if current < _moment(self.manifest.not_before, "authority not_before"):
            raise ChallengerRuntimeError("authority is not yet valid")
        if current >= _moment(self.manifest.expires_at, "authority expires_at"):
            raise ChallengerRuntimeError("authority expired during the run")
        elapsed = (current - self._started_at).total_seconds()
        if elapsed < 0 or elapsed > self.manifest.budget.max_wall_seconds:
            raise ChallengerRuntimeError("authority wall-clock budget exceeded")
        return raw

    def _validate_repository_manifest(self, snapshot: RepositoryBinding) -> None:
        if snapshot.head_commit != self.manifest.repository_head:
            raise ChallengerRuntimeError("source checkout HEAD changed from authority")
        if snapshot.tree_oid != self.manifest.repository_tree:
            raise ChallengerRuntimeError("source checkout tree changed from authority")
        if snapshot.state_digest != canonical_digest({"status": [], "diff": ""}):
            raise ChallengerRuntimeError(
                "source checkout must be clean at the authority boundary"
            )

    def _assert_holdout_commitment(self, holdout: SealedHoldout) -> None:
        try:
            actual = sealed_holdout_commitment(holdout)
        except EvaluationAuthorityError as error:
            raise ChallengerRuntimeError(
                "holdout content cannot be committed"
            ) from error
        if actual != self.manifest.holdout_commitment:
            raise ChallengerRuntimeError(
                "holdout content does not match the authority commitment"
            )

    def _champion_snapshot(
        self,
    ) -> tuple[bytes | None, tuple[tuple[str, str, bytes], ...]]:
        pointer = (
            self.registry.pointer_path.read_bytes()
            if self.registry.pointer_path.is_file()
            else None
        )
        champions: list[tuple[str, str, bytes]] = []
        for role in Role:
            digest = self.registry.champion_digest(role)
            if digest is None:
                raise ChallengerRuntimeError(
                    f"role has no active champion: {role.value}"
                )
            champions.append(
                (role.value, digest, self.registry.artifact_path(digest).read_bytes())
            )
        return pointer, tuple(champions)

    def _assert_immutable(
        self,
        before_repository: RepositoryBinding,
        before_champions: tuple[bytes | None, tuple[tuple[str, str, bytes], ...]],
    ) -> None:
        after_repository = capture_repository_binding(self.repository_root)
        if after_repository != before_repository:
            raise ChallengerRuntimeError(
                "source checkout changed during challenger operation"
            )
        if self._champion_snapshot() != before_champions:
            raise ChallengerRuntimeError(
                "champion pointer or active champion bytes changed during challenger operation"
            )

    def _write_record(self, kind: str, document: Mapping[str, Any]) -> tuple[Path, str]:
        material = {"schema_version": 1, "kind": kind, **dict(document)}
        digest = canonical_digest(material)
        directory = self._evidence_root / kind
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{digest[7:]}.json"
        payload = canonical_bytes(material) + b"\n"
        try:
            with path.open("xb") as handle:
                handle.write(payload)
                handle.flush()
        except FileExistsError:
            if path.read_bytes() != payload:
                raise ChallengerRuntimeError(
                    f"retained {kind} record was mutated"
                ) from None
        return path.resolve(), digest

    def propose(
        self,
        finding: ChallengerFinding,
        *,
        prior_outcome: AuthorityEvaluationOutcome | None = None,
    ) -> ChallengerProposal:
        """Turn a finding into an owned, falsifiable generation-1 hypothesis."""

        if prior_outcome is not None:
            raise ChallengerRuntimeError(
                "use reenter() to create a generation-2 proposal"
            )
        return self._propose(finding, generation=1, prior_outcome_digest=None)

    def _propose(
        self,
        finding: ChallengerFinding,
        *,
        generation: int,
        prior_outcome_digest: str | None,
    ) -> ChallengerProposal:
        now = self._check_budget_clock()
        if not isinstance(finding, ChallengerFinding):
            raise ChallengerRuntimeError("proposal requires a ChallengerFinding")
        if finding.owner_id != self.manifest.identities.proposer_id:
            raise ChallengerRuntimeError(
                "finding is not owned by the authorized proposer"
            )
        if _moment(finding.expires_at, "finding expires_at") <= _moment(
            now, "runtime current time"
        ):
            raise ChallengerRuntimeError("finding expired before proposal")
        if len(self._proposals) >= self.manifest.budget.max_candidates:
            raise ChallengerRuntimeError("candidate budget exceeded")
        parent = self.manifest.champion_digest(finding.role)
        if self.registry.champion_digest(finding.role) != parent:
            raise ChallengerRuntimeError("current champion changed before proposal")
        statement = (
            f"For {finding.role}, {finding.proposed_change}; expected effect: "
            f"reduce {finding.error_class}."
        )
        hypothesis_document = {
            "finding_id": finding.finding_id,
            "role": finding.role,
            "owner_id": finding.owner_id,
            "statement": statement,
            "falsifier": finding.falsifier,
            "parent_champion_digest": parent,
            "evidence_refs": finding.evidence_refs,
            "generation": generation,
            "prior_outcome_digest": prior_outcome_digest,
        }
        hypothesis = OwnedHypothesis(
            hypothesis_id="HYP-" + canonical_digest(hypothesis_document)[7:23],
            finding_id=finding.finding_id,
            role=finding.role,
            owner_id=finding.owner_id,
            statement=statement,
            falsifier=finding.falsifier,
            parent_champion_digest=parent,
            evidence_refs=finding.evidence_refs,
            generation=generation,
            prior_outcome_digest=prior_outcome_digest,
        )
        lesson_id = (
            f"{finding.finding_id}-g{generation}-"
            f"{hypothesis.hypothesis_id.removeprefix('HYP-')[:8]}"
        )
        lesson = AcceptedLesson(
            lesson_id=lesson_id,
            source_episode_id=finding.source_episode_id,
            outcome="failure",
            error_class=finding.error_class,
            applicability=(f"prompt:{finding.role}",),
            confidence=1.0,
            provenance=tuple(
                dict.fromkeys(
                    (
                        *finding.evidence_refs,
                        *(
                            (f"outcome:{prior_outcome_digest}",)
                            if prior_outcome_digest is not None
                            else ()
                        ),
                    )
                )
            ),
            expires_at=finding.expires_at,
        )
        proposal_digest = canonical_digest({"hypothesis": hypothesis, "lesson": lesson})
        proposal = ChallengerProposal(
            hypothesis=hypothesis,
            lesson=lesson,
            proposal_digest=proposal_digest,
        )
        if proposal_digest in self._proposals:
            raise ChallengerRuntimeError("proposal is already registered")
        self._proposals[proposal_digest] = proposal
        self._write_record(
            "proposal",
            {
                "authority_manifest_digest": self.manifest.manifest_digest,
                "proposal": proposal,
                "created_at": now,
            },
        )
        return proposal

    def seal_evaluation(
        self,
        proposal: ChallengerProposal,
        *,
        holdout: SealedHoldout,
        prediction: Mapping[str, Any],
        surfaces: Sequence[PlannedSurface],
    ) -> EvaluationPlanSeal:
        """Seal evaluator prediction and complete harness geometry before build."""

        sealed_at = self._check_budget_clock()
        registered = self._proposals.get(proposal.proposal_digest)
        if registered != proposal:
            raise ChallengerRuntimeError("proposal is not registered in this runtime")
        if any(
            plan.proposal_digest == proposal.proposal_digest
            for plan in self._plans.values()
        ):
            raise ChallengerRuntimeError("proposal already has a sealed evaluation")
        if not isinstance(holdout, SealedHoldout):
            raise ChallengerRuntimeError("evaluation seal requires a SealedHoldout")
        self._assert_holdout_commitment(holdout)
        if holdout._holdout_id != self.manifest.holdout_id:
            raise ChallengerRuntimeError(
                "holdout id does not match authority commitment"
            )
        ordering = holdout.ordering
        if (
            holdout.violations
            or ordering["seal_sequence"] is not None
            or ordering["reveal_sequence"] is not None
        ):
            raise ChallengerRuntimeError(
                "holdout was accessed or sealed before evaluation-plan sealing"
            )
        if not isinstance(prediction, Mapping) or not prediction:
            raise ChallengerRuntimeError(
                "sealed prediction must be a non-empty mapping"
            )
        planned = tuple(surfaces)
        if not planned or any(not isinstance(item, PlannedSurface) for item in planned):
            raise ChallengerRuntimeError("evaluation plan requires planned surfaces")
        keys = {(item.kind, item.name) for item in planned}
        if len(keys) != len(planned):
            raise ChallengerRuntimeError("evaluation plan surfaces must be unique")
        kinds = {item.kind for item in planned}
        if kinds != set(SurfaceKind):
            raise ChallengerRuntimeError(
                "evaluation plan must include held-out, PIT, adversarial, and comparator surfaces"
            )
        holdout_seal = holdout.seal_prediction(
            self.manifest.identities.evaluator_id, prediction
        )
        hypothesis = proposal.hypothesis
        unsigned = {
            "authority_manifest_digest": self.manifest.manifest_digest,
            "proposal_digest": proposal.proposal_digest,
            "hypothesis_id": hypothesis.hypothesis_id,
            "role": hypothesis.role,
            "generation": hypothesis.generation,
            "parent_champion_digest": hypothesis.parent_champion_digest,
            "prior_outcome_digest": hypothesis.prior_outcome_digest,
            "surfaces": [
                {"kind": item.kind.value, "name": item.name} for item in planned
            ],
            "comparators": [item.to_document() for item in self.manifest.comparators],
            "holdout_id": self.manifest.holdout_id,
            "holdout_commitment": self.manifest.holdout_commitment,
            "prediction_digest": holdout_seal.prediction_digest,
            "seal_sequence": holdout_seal.sequence,
            "contract_fingerprint": self.manifest.contract_fingerprint,
            "harness_fingerprint": self.manifest.harness_fingerprint,
            "repository_head": self.manifest.repository_head,
            "repository_tree": self.manifest.repository_tree,
            "sealed_by": self.manifest.identities.evaluator_id,
            "sealed_at": sealed_at,
        }
        plan_digest = canonical_digest(unsigned)
        plan_id = "PLAN-" + plan_digest[7:23]
        record_path, record_digest = self._write_record(
            "evaluation-plan",
            {**unsigned, "plan_id": plan_id, "plan_digest": plan_digest},
        )
        # The record digest covers its kind as well; the semantic plan digest is
        # what evidence envelopes depend on.
        if record_digest == plan_digest:
            raise ChallengerRuntimeError("plan and record digest domains collided")
        plan = EvaluationPlanSeal(
            plan_id=plan_id,
            plan_digest=plan_digest,
            proposal_digest=proposal.proposal_digest,
            hypothesis_id=hypothesis.hypothesis_id,
            generation=hypothesis.generation,
            prior_outcome_digest=hypothesis.prior_outcome_digest,
            surfaces=planned,
            holdout_id=self.manifest.holdout_id,
            holdout_seal=holdout_seal,
            record_path=record_path,
        )
        self._plans[plan_digest] = plan
        return plan

    def materialize(
        self,
        proposal: ChallengerProposal,
        plan: EvaluationPlanSeal,
        *,
        holdout: SealedHoldout,
    ) -> MaterializedChallenger:
        """Register one prompt artifact only after an intact pre-build seal."""

        created_at = self._check_budget_clock()
        if self._proposals.get(proposal.proposal_digest) != proposal:
            raise ChallengerRuntimeError("proposal is not registered")
        if self._plans.get(plan.plan_digest) != plan:
            raise ChallengerRuntimeError("evaluation plan is not registered")
        if plan.proposal_digest != proposal.proposal_digest:
            raise ChallengerRuntimeError("evaluation plan belongs to another proposal")
        if plan.plan_digest in self._materialized:
            raise ChallengerRuntimeError("evaluation plan was already materialized")
        self._assert_holdout_commitment(holdout)
        if holdout._holdout_id != plan.holdout_id:
            raise ChallengerRuntimeError("materialization holdout is not plan-bound")
        if holdout._seal != plan.holdout_seal:
            raise ChallengerRuntimeError("materialization holdout seal was replaced")
        ordering = holdout.ordering
        if holdout.violations or ordering["reveal_sequence"] is not None:
            raise ChallengerRuntimeError(
                "holdout was revealed before challenger materialization"
            )

        role = proposal.hypothesis.role
        champion_content, champion_digest = self.registry.champion_prompt(role)
        if champion_digest != proposal.hypothesis.parent_champion_digest:
            raise ChallengerRuntimeError("champion changed before materialization")
        expected_content = champion_content + (
            f"\n\nLesson {proposal.lesson.lesson_id}: avoid "
            f"{proposal.lesson.error_class}; evidence: {proposal.lesson.provenance[0]}"
        )
        if (
            len(expected_content.encode("utf-8"))
            > self.manifest.budget.max_prompt_bytes
        ):
            raise ChallengerRuntimeError("candidate prompt-byte budget exceeded")

        repository_before = capture_repository_binding(self.repository_root)
        self._validate_repository_manifest(repository_before)
        champions_before = self._champion_snapshot()
        result = self._generator.generate([proposal.lesson], champions={})
        if result.rejections or len(result.challengers) != 1:
            raise ChallengerRuntimeError(
                "challenger generator did not materialize exactly one prompt"
            )
        spec = result.challengers[0]
        if spec.content != expected_content or spec.content_digest != prompt_digest(
            expected_content
        ):
            raise ChallengerRuntimeError(
                "materialized prompt differs from sealed proposal"
            )
        self._assert_immutable(repository_before, champions_before)

        binding = CandidateAuthorityBinding(
            candidate_id=spec.challenger_id,
            candidate_digest=spec.content_digest,
            role=role,
            parent_champion_digest=spec.champion_ref,
            authority_manifest_digest=self.manifest.manifest_digest,
            generation=proposal.hypothesis.generation,
        )
        self.manifest.validate_candidate(
            binding, current_champion_digest=champion_digest
        )
        experiment_id = f"challenger:{proposal.lesson.lesson_id}"
        descriptor = ChallengerDescriptor(
            challenger_id=spec.challenger_id,
            parent_champion_id=spec.champion_ref,
            change_ref=self.registry.artifact_path(spec.content_digest).as_posix(),
            proposal_digest=spec.content_digest,
        )
        material = {
            "authority_manifest_digest": self.manifest.manifest_digest,
            "plan_digest": plan.plan_digest,
            "proposal_digest": proposal.proposal_digest,
            "candidate": binding,
            "challenger_spec": spec,
            "experiment_id": experiment_id,
            "materialized_at": created_at,
            "source_before": repository_before,
            "source_after": capture_repository_binding(self.repository_root),
            "champion_pointer_unchanged": True,
        }
        record_path, materialization_digest = self._write_record(
            "materialization", material
        )
        materialized = MaterializedChallenger(
            proposal=proposal,
            plan_digest=plan.plan_digest,
            spec=spec,
            descriptor=descriptor,
            binding=binding,
            experiment_id=experiment_id,
            materialization_digest=materialization_digest,
            record_path=record_path,
        )
        self._materialized[plan.plan_digest] = materialized
        return materialized

    def evaluate(
        self,
        materialized: MaterializedChallenger,
        plan: EvaluationPlanSeal,
        *,
        holdout: SealedHoldout,
        surfaces: Sequence[BoundSurfaceEvidence],
        qualification_receipts: Sequence[EvidenceReceipt],
        issuer_authorities: Sequence[IssuerAuthority],
        candidate_trust_domain: str,
        target_level: QualificationLevel,
        qualification_policy: QualificationPolicy = QualificationPolicy(),
        as_of: str,
    ) -> AuthorityEvaluationOutcome:
        """Verify external receipts, then delegate measurement to EvaluationRuntime."""

        evaluation_time = self._check_budget_clock()
        if _moment(as_of, "qualification as_of") != _moment(
            evaluation_time, "runtime evaluation time"
        ):
            raise ChallengerRuntimeError(
                "qualification as_of must equal the runtime clock"
            )
        extra_receipts = tuple(qualification_receipts)
        if any(not isinstance(item, EvidenceReceipt) for item in extra_receipts):
            raise ChallengerRuntimeError(
                "qualification_receipts must contain EvidenceReceipt values"
            )
        retained_qualification = tuple(
            (receipt.receipt_id, receipt.artifact_digest) for receipt in extra_receipts
        )
        if len(self._outcomes) >= self.manifest.budget.max_evaluations:
            raise ChallengerRuntimeError("evaluation budget exceeded")
        if self._materialized.get(plan.plan_digest) != materialized:
            raise ChallengerRuntimeError("candidate is not materialized by this plan")
        if materialized.plan_digest != plan.plan_digest:
            raise ChallengerRuntimeError("candidate and plan bindings differ")
        self._assert_holdout_commitment(holdout)
        if holdout._holdout_id != plan.holdout_id or holdout._seal != plan.holdout_seal:
            raise ChallengerRuntimeError("evaluation holdout is not plan-bound")
        ordering = holdout.ordering
        if (
            holdout.violations
            or ordering["reveal_sequence"] is None
            or ordering["reveal_sequence"] <= plan.holdout_seal.sequence
        ):
            return self._retain_outcome(
                materialized,
                plan,
                verdict=EvaluationVerdict.QUARANTINE,
                reasons=(
                    "holdout was not revealed through the intact post-build seal",
                ),
                qualification=None,
                evaluation_record=None,
                surface_receipts=(),
                qualification_receipts=retained_qualification,
            )
        if extra_receipts:
            return self._retain_outcome(
                materialized,
                plan,
                verdict=EvaluationVerdict.QUARANTINE,
                reasons=(
                    "separate qualification receipts are unsupported until a "
                    "schema-specific externally attestable evidence envelope exists",
                ),
                qualification=None,
                evaluation_record=None,
                surface_receipts=tuple(
                    (item.receipt.receipt_id, item.receipt.artifact_digest)
                    for item in surfaces
                    if isinstance(item, BoundSurfaceEvidence)
                ),
                qualification_receipts=retained_qualification,
            )
        current = self.registry.champion_digest(materialized.binding.role)
        if current is None:
            raise ChallengerRuntimeError("candidate role has no current champion")
        try:
            self.manifest.validate_candidate(
                materialized.binding, current_champion_digest=current
            )
            bound = validate_surface_set(
                surfaces,
                store=self.artifact_store,
                manifest=self.manifest,
                candidate=materialized.binding,
                evaluation_plan_digest=plan.plan_digest,
                prior_outcome_digest=plan.prior_outcome_digest,
            )
            actual_protocol = tuple(
                sorted((item.surface.kind.value, item.surface.name) for item in bound)
            )
            sealed_protocol = tuple(
                sorted((item.kind.value, item.name) for item in plan.surfaces)
            )
            if actual_protocol != sealed_protocol:
                raise EvaluationAuthorityError(
                    "surface set differs from the sealed evaluation protocol"
                )
            for item in bound:
                if (
                    item.receipt.claim_id
                    != materialized.proposal.hypothesis.hypothesis_id
                ):
                    raise EvaluationAuthorityError(
                        "surface receipt is bound to the wrong hypothesis"
                    )
                if not item.receipt.passed:
                    raise EvaluationAuthorityError(
                        "failed surface receipt cannot provide evaluation measurements"
                    )
        except EvaluationAuthorityError as error:
            return self._retain_outcome(
                materialized,
                plan,
                verdict=EvaluationVerdict.QUARANTINE,
                reasons=(str(error),),
                qualification=None,
                evaluation_record=None,
                surface_receipts=tuple(
                    (item.receipt.receipt_id, item.receipt.artifact_digest)
                    for item in surfaces
                    if isinstance(item, BoundSurfaceEvidence)
                ),
                qualification_receipts=retained_qualification,
            )

        surface_receipts = tuple(item.receipt for item in bound)
        retained_receipts = tuple(
            (receipt.receipt_id, receipt.artifact_digest)
            for receipt in surface_receipts
        )
        qualification = qualify_claim(
            QualificationRequest(
                claim_id=materialized.proposal.hypothesis.hypothesis_id,
                candidate_digest=materialized.binding.candidate_digest,
                candidate_trust_domain=_text(
                    candidate_trust_domain, "candidate trust domain"
                ),
                target_level=target_level,
                as_of=evaluation_time,
            ),
            surface_receipts,
            tuple(issuer_authorities),
            policy=qualification_policy,
        )
        receipt_ids = tuple(item.receipt.receipt_id for item in bound)
        if not set(receipt_ids).issubset(set(qualification.accepted_receipt_ids)):
            return self._retain_outcome(
                materialized,
                plan,
                verdict=EvaluationVerdict.QUARANTINE,
                reasons=(
                    "qualification did not accept every bound surface receipt",
                    *qualification.failures,
                ),
                qualification=qualification,
                evaluation_record=None,
                surface_receipts=retained_receipts,
                qualification_receipts=retained_qualification,
            )
        if qualification.disposition is QualificationDisposition.QUARANTINE:
            return self._retain_outcome(
                materialized,
                plan,
                verdict=EvaluationVerdict.QUARANTINE,
                reasons=qualification.failures
                or ("qualification quarantined candidate",),
                qualification=qualification,
                evaluation_record=None,
                surface_receipts=retained_receipts,
                qualification_receipts=retained_qualification,
            )
        if not qualification.qualified:
            return self._retain_outcome(
                materialized,
                plan,
                verdict=EvaluationVerdict.RETEST,
                reasons=qualification.missing_requirements
                or ("qualification deferred candidate",),
                qualification=qualification,
                evaluation_record=None,
                surface_receipts=retained_receipts,
                qualification_receipts=retained_qualification,
            )

        repository_before = capture_repository_binding(self.repository_root)
        champions_before = self._champion_snapshot()
        record = self.evaluation_runtime.evaluate(
            materialized.descriptor,
            EvaluationIdentities(
                self.manifest.identities.proposer_id,
                self.manifest.identities.builder_id,
                self.manifest.identities.evaluator_id,
            ),
            [item.surface for item in bound],
            holdout,
            evidence_root=self._evidence_root / "legacy-evaluation",
        )
        self._assert_immutable(repository_before, champions_before)
        return self._retain_outcome(
            materialized,
            plan,
            verdict=record.verdict,
            reasons=record.reasons,
            qualification=qualification,
            evaluation_record=record,
            surface_receipts=retained_receipts,
            qualification_receipts=retained_qualification,
        )

    def _retain_outcome(
        self,
        materialized: MaterializedChallenger,
        plan: EvaluationPlanSeal,
        *,
        verdict: EvaluationVerdict,
        reasons: tuple[str, ...],
        qualification: QualificationDecision | None,
        evaluation_record: EvaluationRecord | None,
        surface_receipts: tuple[tuple[str, str], ...],
        qualification_receipts: tuple[tuple[str, str], ...],
    ) -> AuthorityEvaluationOutcome:
        reasons = tuple(dict.fromkeys(reasons))
        if not reasons:
            reasons = ("evaluation produced no reason",)
        document = {
            "authority_manifest_digest": self.manifest.manifest_digest,
            "plan_digest": plan.plan_digest,
            "materialization_digest": materialized.materialization_digest,
            "candidate_digest": materialized.binding.candidate_digest,
            "generation": materialized.binding.generation,
            "prior_outcome_digest": plan.prior_outcome_digest,
            "verdict": verdict.value,
            "reasons": reasons,
            "qualification": qualification,
            "evaluation_record_ref": (
                _file_reference(evaluation_record.record_path)
                if evaluation_record is not None
                else None
            ),
            "surface_receipts": [
                {"receipt_id": receipt_id, "artifact_digest": artifact_digest}
                for receipt_id, artifact_digest in surface_receipts
            ],
            "qualification_receipts": [
                {"receipt_id": receipt_id, "artifact_digest": artifact_digest}
                for receipt_id, artifact_digest in qualification_receipts
            ],
        }
        record_path, outcome_digest = self._write_record("outcome", document)
        outcome = AuthorityEvaluationOutcome(
            materialized=materialized,
            plan_digest=plan.plan_digest,
            verdict=verdict,
            reasons=reasons,
            qualification=qualification,
            evaluation_record=evaluation_record,
            surface_receipts=surface_receipts,
            qualification_receipts=qualification_receipts,
            prior_outcome_digest=plan.prior_outcome_digest,
            outcome_digest=outcome_digest,
            record_path=record_path,
        )
        self._outcomes[outcome_digest] = outcome
        return outcome

    def submit_appeal(
        self,
        outcome: AuthorityEvaluationOutcome,
        *,
        court_history: CourtHistory,
        court_case_id: str,
        decision_id: str,
    ) -> ChallengerAppeal:
        """Submit a court-backed decision without applying it to the pointer."""

        self._check_budget_clock()
        if self._outcomes.get(outcome.outcome_digest) != outcome:
            raise ChallengerRuntimeError(
                "evaluation outcome is not retained by runtime"
            )
        if not isinstance(court_history, CourtHistory):
            raise ChallengerRuntimeError("appeal requires a CourtHistory")
        if outcome.verdict is EvaluationVerdict.KEEP:
            raise KeepPromotionUnsupportedError(
                "V2 KEEP promotion is deferred until externally attestable "
                "qualification evidence exists"
            )
        if outcome.qualification is None:
            raise ChallengerRuntimeError(
                "unqualified outcome cannot enter promotion authority"
            )
        record = next(
            (
                item
                for item in court_history.records
                if item.case.case_id == court_case_id
            ),
            None,
        )
        if record is None:
            raise ChallengerRuntimeError("court case is not present in history")
        verdict_map = {
            EvaluationVerdict.KEEP: ExperimentVerdict.KEEP,
            EvaluationVerdict.RETEST: ExperimentVerdict.RETEST,
            EvaluationVerdict.DISCARD: ExperimentVerdict.DISCARD,
            EvaluationVerdict.QUARANTINE: ExperimentVerdict.QUARANTINE,
        }
        materialized = outcome.materialized
        evidence_refs = tuple(
            dict.fromkeys(
                (
                    _file_reference(outcome.record_path),
                    _file_reference(materialized.record_path),
                    *(
                        f"artifact:{artifact_digest}"
                        for artifact_digest in outcome.surface_artifact_digests
                    ),
                    *(
                        f"artifact:{artifact_digest}"
                        for artifact_digest in outcome.qualification_artifact_digests
                    ),
                )
            )
        )
        candidate = PromotionCandidate(
            candidate_id=materialized.binding.candidate_id,
            role=materialized.binding.role,
            experiment_id=materialized.experiment_id,
            artifact_digest=materialized.binding.candidate_digest,
            parent_champion_digest=materialized.binding.parent_champion_digest,
            proposer_id=self.manifest.identities.proposer_id,
            builder_id=self.manifest.identities.builder_id,
            evidence_refs=evidence_refs,
        )
        decision = PromotionDecision(
            decision_id=_text(decision_id, "decision_id"),
            court_case_id=_text(court_case_id, "court_case_id"),
            candidate=candidate,
            verdict=verdict_map[outcome.verdict],
            judge_id=self.manifest.identities.judge_id,
            evaluator_id=self.manifest.identities.evaluator_id,
            reasons=outcome.reasons,
            contract_fingerprint=self.manifest.contract_fingerprint,
        )
        repository_before = capture_repository_binding(self.repository_root)
        champions_before = self._champion_snapshot()
        self.promotion_authority.submit(decision, court_history=court_history)
        self._assert_immutable(repository_before, champions_before)
        appeal_id = (
            "APPEAL-"
            + canonical_digest(
                {
                    "decision_id": decision.decision_id,
                    "outcome_digest": outcome.outcome_digest,
                    "court_disposition": record.verdict.disposition.value,
                }
            )[7:23]
        )
        path, appeal_digest = self._write_record(
            "appeal",
            {
                "appeal_id": appeal_id,
                "outcome_digest": outcome.outcome_digest,
                "decision_binding_digest": decision.binding_digest,
                "decision_id": decision.decision_id,
                "court_case_id": court_case_id,
                "court_disposition": record.verdict.disposition.value,
                "pointer_unchanged": True,
            },
        )
        appeal = ChallengerAppeal(
            appeal_id=appeal_id,
            outcome_digest=outcome.outcome_digest,
            decision=decision,
            court_disposition=record.verdict.disposition,
            appeal_digest=appeal_digest,
            record_path=path,
        )
        self._appeals[outcome.outcome_digest] = appeal
        return appeal

    def reenter(
        self,
        outcome: AuthorityEvaluationOutcome,
        finding: ChallengerFinding,
        *,
        appeal: ChallengerAppeal | None = None,
    ) -> ChallengerProposal:
        """Return a deferred generation-1 idea to the beginning exactly once."""

        self._check_budget_clock()
        if self._outcomes.get(outcome.outcome_digest) != outcome:
            raise ChallengerRuntimeError("re-entry outcome is not retained")
        if outcome.materialized.binding.generation != 1:
            raise ChallengerRuntimeError("only generation-1 can re-enter")
        if outcome.outcome_digest in self._reentered_outcomes:
            raise ChallengerRuntimeError("outcome already used for re-entry")
        eligible = outcome.verdict is EvaluationVerdict.RETEST
        if appeal is not None:
            if self._appeals.get(outcome.outcome_digest) != appeal:
                raise ChallengerRuntimeError("re-entry appeal is not retained")
            eligible = eligible or appeal.court_disposition is CourtDisposition.DEFER
        if not eligible:
            raise ChallengerRuntimeError(
                "generation-2 re-entry requires RETEST or a DEFER court disposition"
            )
        if outcome.outcome_digest not in finding.evidence_refs:
            raise ChallengerRuntimeError(
                "generation-2 finding must cite the retained prior outcome digest"
            )
        proposal = self._propose(
            finding,
            generation=2,
            prior_outcome_digest=outcome.outcome_digest,
        )
        self._reentered_outcomes.add(outcome.outcome_digest)
        return proposal

    @property
    def retained_outcomes(self) -> tuple[AuthorityEvaluationOutcome, ...]:
        return tuple(self._outcomes.values())

    @property
    def retained_appeals(self) -> tuple[ChallengerAppeal, ...]:
        return tuple(self._appeals.values())
