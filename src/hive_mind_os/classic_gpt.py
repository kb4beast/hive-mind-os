from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256
from typing import Mapping

from .models import Role
from .receipts import FileReceiptValidator, ReceiptReference


class SimulationPhase(StrEnum):
    INTAKE = "intake"
    DISCOVER = "discover"
    DESIGN = "design"
    BUILD = "build"
    VALIDATE = "validate"
    INTEGRATE = "integrate"
    MAINTAIN = "maintain"
    OPTIMIZE = "optimize"
    COMPLETE = "complete"
    BLOCKED = "blocked"
    QUARANTINED = "quarantined"


class ActionKind(StrEnum):
    REASONING = "reasoning"
    READ = "read"
    WRITE = "write"
    COMMAND = "command"
    NETWORK = "network"
    GIT = "git"
    MESSAGE = "message"
    DEPLOY = "deploy"


SIDE_EFFECTING_ACTIONS = frozenset(
    {
        ActionKind.WRITE,
        ActionKind.COMMAND,
        ActionKind.NETWORK,
        ActionKind.GIT,
        ActionKind.MESSAGE,
        ActionKind.DEPLOY,
    }
)


@dataclass(frozen=True, slots=True)
class ClassicGptSourceFile:
    path: str
    purpose: str
    priority: int
    required_markers: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.path.strip() or not self.purpose.strip():
            raise ValueError("source file path and purpose are required")
        if self.priority < 0:
            raise ValueError("source priority cannot be negative")
        if not self.required_markers or any(not marker.strip() for marker in self.required_markers):
            raise ValueError("source files require non-empty validation markers")


@dataclass(frozen=True, slots=True)
class SourcePackAudit:
    valid: bool
    issues: tuple[str, ...] = ()


DEFAULT_CLASSIC_GPT_FILES: tuple[ClassicGptSourceFile, ...] = (
    ClassicGptSourceFile(
        "gpt_sources/00_HIVE_MIND_SYSTEM_INSTRUCTIONS.md",
        "Binding operating instructions and authority boundary for a classic GPT session.",
        0,
        (
            "Evidence before authority",
            "Never claim a tool action occurred without a receipt",
            "MISSION_STATE",
            "COURT_RECORD",
        ),
    ),
    ClassicGptSourceFile(
        "gpt_sources/01_RUNTIME_STATE_SCHEMA.json",
        "Portable mission, role, court, evidence, budget, and handoff state schema.",
        1,
        (
            '"schema_version"',
            '"mission"',
            '"role_runs"',
            '"court_cases"',
            '"tool_receipts"',
            '"next_action"',
        ),
    ),
    ClassicGptSourceFile(
        "gpt_sources/02_ROLE_AND_COURT_PROTOCOL.md",
        "Eight-role execution passes, conflict-of-interest rules, and courtroom procedure.",
        2,
        (
            "Orchestrator",
            "Explorer",
            "Architect",
            "Builder",
            "Curator",
            "Integrator",
            "Steward",
            "Optimizer",
            "Cross-Examiner",
        ),
    ),
    ClassicGptSourceFile(
        "gpt_sources/03_TOOL_EVIDENCE_AND_HANDOFF_PROTOCOL.md",
        "Receipt rules, completion semantics, context compaction, resume, and handoff protocol.",
        3,
        (
            "PROPOSED_ACTION",
            "TOOL_RECEIPT",
            "UNVERIFIED",
            "HANDOFF_PACKET",
            "Do not convert a proposal into a completed action",
        ),
    ),
    ClassicGptSourceFile(
        "gpt_sources/manifest.json",
        "Machine-readable load order and integrity manifest for the simulation pack.",
        4,
        (
            '"pack_id"',
            '"load_order"',
            '"authority_model"',
            '"simulation_limit"',
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class ClassicGptSourcePack:
    schema_version: int = 1
    files: tuple[ClassicGptSourceFile, ...] = DEFAULT_CLASSIC_GPT_FILES

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(f"unsupported classic GPT source-pack schema: {self.schema_version}")
        paths = [item.path for item in self.files]
        priorities = [item.priority for item in self.files]
        if len(paths) != len(set(paths)):
            raise ValueError("classic GPT source pack contains duplicate paths")
        if len(priorities) != len(set(priorities)):
            raise ValueError("classic GPT source pack contains duplicate priorities")
        if priorities != sorted(priorities):
            raise ValueError("classic GPT source pack must be stored in load order")

    @property
    def fingerprint(self) -> str:
        canonical = "\n".join(
            (
                str(self.schema_version),
                *(
                    "|".join((item.path, item.purpose, str(item.priority), *item.required_markers))
                    for item in self.files
                ),
            )
        )
        return sha256(canonical.encode("utf-8")).hexdigest()

    def audit(self, documents: Mapping[str, str]) -> SourcePackAudit:
        issues: list[str] = []
        expected = {item.path for item in self.files}
        unknown = set(documents) - expected
        if unknown:
            issues.append("unexpected source files: " + ", ".join(sorted(unknown)))

        for item in self.files:
            content = documents.get(item.path)
            if content is None:
                issues.append(f"missing source file: {item.path}")
                continue
            if not content.strip():
                issues.append(f"empty source file: {item.path}")
                continue
            for marker in item.required_markers:
                if marker not in content:
                    issues.append(f"{item.path} missing required marker: {marker}")
        return SourcePackAudit(not issues, tuple(issues))


@dataclass(frozen=True, slots=True)
class SimulatedAction:
    id: str
    kind: ActionKind
    description: str
    actor_id: str
    receipt_ref: ReceiptReference | None = None

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.description.strip() or not self.actor_id.strip():
            raise ValueError("simulated actions require action, actor, and description identity")
        if self.receipt_ref is not None and not isinstance(self.receipt_ref, ReceiptReference):
            raise TypeError("receipt_ref must be a ReceiptReference, not an unverified label")

    @property
    def digest(self) -> str:
        payload = json.dumps(
            {
                "schema_version": 1,
                "id": self.id,
                "kind": self.kind.value,
                "description": self.description,
                "actor_id": self.actor_id,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return f"sha256:{sha256(payload).hexdigest()}"


@dataclass(frozen=True, slots=True)
class ClassicGptTurn:
    mission_id: str
    phase: SimulationPhase
    active_role: Role
    actor_id: str
    state_ref: str
    evidence_refs: tuple[str, ...]
    actions: tuple[SimulatedAction, ...] = ()
    completed_roles: tuple[Role, ...] = ()
    verifier_ids: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    next_action: str = ""
    confidence: float = 0.0
    source_pack_fingerprint: str = ""

    def __post_init__(self) -> None:
        required = (self.mission_id, self.actor_id, self.state_ref, self.next_action)
        if any(not value.strip() for value in required):
            raise ValueError("mission, actor, state, and next action are required")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class SimulationDecision:
    compliant: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)


class ClassicGptSimulationGate:
    """Fail-closed checks for simulating Hive Mind OS in a single classic GPT session."""

    def __init__(
        self,
        source_pack: ClassicGptSourcePack | None = None,
        receipt_validator: FileReceiptValidator | None = None,
    ) -> None:
        self.source_pack = source_pack or ClassicGptSourcePack()
        self.receipt_validator = receipt_validator

    def evaluate(self, turn: ClassicGptTurn) -> SimulationDecision:
        reasons: list[str] = []
        receipt_results: dict[str, bool] = {}
        used_receipt_references: set[tuple[str, str]] = set()
        used_receipt_ids: set[str] = set()
        if turn.source_pack_fingerprint != self.source_pack.fingerprint:
            reasons.append("classic GPT source pack changed or was not loaded")

        if not turn.evidence_refs:
            reasons.append("turn has no evidence references")

        for action in turn.actions:
            if action.kind not in SIDE_EFFECTING_ACTIONS:
                continue
            if turn.phase is not SimulationPhase.COMPLETE and action.actor_id != turn.actor_id:
                reasons.append(
                    f"side-effecting action {action.id} actor does not match the active turn"
                )
            if action.receipt_ref is None:
                reasons.append(
                    f"side-effecting action {action.id} lacks an external tool receipt"
                )
                continue
            if self.receipt_validator is None:
                reasons.append(
                    f"side-effecting action {action.id} receipt has no independent validator"
                )
                continue

            reference_identity = (action.receipt_ref.path, action.receipt_ref.digest)
            if reference_identity in used_receipt_references:
                reasons.append(f"side-effecting action {action.id} reuses another action receipt")
                continue
            used_receipt_references.add(reference_identity)

            validation = self.receipt_validator.validate(
                action.receipt_ref,
                mission_id=turn.mission_id,
                state_ref=turn.state_ref,
                actor_id=action.actor_id,
                action_id=action.id,
                action_kind=action.kind.value,
                action_digest=action.digest,
            )
            if not validation.valid:
                for issue in validation.issues:
                    reasons.append(f"side-effecting action {action.id}: {issue}")
                continue
            if validation.receipt_id in used_receipt_ids:
                reasons.append(f"side-effecting action {action.id} reuses another receipt id")
                continue
            if validation.receipt_id:
                used_receipt_ids.add(validation.receipt_id)
            receipt_results[action.id] = validation.succeeded

        actor_ids = {turn.actor_id}
        verifier_ids = {item for item in turn.verifier_ids if item}
        if actor_ids & verifier_ids:
            reasons.append("acting identity attempted to verify its own work")

        if turn.phase is SimulationPhase.COMPLETE:
            missing_roles = set(Role) - set(turn.completed_roles)
            if missing_roles:
                reasons.append(
                    "completion is missing role passes: "
                    + ", ".join(sorted(role.value for role in missing_roles))
                )
            if not verifier_ids:
                reasons.append("completion lacks independent verification")
            if turn.blockers:
                reasons.append("completion declared while blockers remain")
            for action in turn.actions:
                if action.kind in SIDE_EFFECTING_ACTIONS and not receipt_results.get(action.id, False):
                    reasons.append(
                        f"completion lacks a successful receipt for side-effecting action {action.id}"
                    )

        if turn.phase is SimulationPhase.QUARANTINED and not turn.blockers:
            reasons.append("quarantined turn must preserve quarantine reasons")

        return SimulationDecision(not reasons, tuple(dict.fromkeys(reasons)))

    def require(self, turn: ClassicGptTurn) -> None:
        decision = self.evaluate(turn)
        if not decision.compliant:
            raise RuntimeError("; ".join(decision.reasons))
