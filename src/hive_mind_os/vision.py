from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256

from .models import Role


class LifecycleStage(StrEnum):
    DISCOVER = "discover"
    DESIGN = "design"
    BUILD = "build"
    VALIDATE = "validate"
    GROW = "grow"
    MAINTAIN = "maintain"
    INTEGRATE = "integrate"


class SystemCapability(StrEnum):
    DECOMPOSE_OUTCOMES = "decompose_outcomes"
    INGEST_SOURCES = "ingest_sources"
    EXTRACT_ATOMIC_IDEAS = "extract_atomic_ideas"
    LITIGATE_IDEAS = "litigate_ideas"
    TRACE_REQUIREMENTS_TO_TESTS = "trace_requirements_to_tests"
    SEARCH_WEB = "search_web"
    SCOUT_REPOSITORIES = "scout_repositories"
    INSPECT_REPOSITORY = "inspect_repository"
    REPLAY_HISTORY_POINT_IN_TIME = "replay_history_point_in_time"
    GENERATE_HYPOTHESES = "generate_hypotheses"
    PROPOSE_IMPROVEMENTS = "propose_improvements"
    MODIFY_CODE = "modify_code"
    RUN_COMMANDS = "run_commands"
    RUN_TESTS = "run_tests"
    OPEN_PULL_REQUEST = "open_pull_request"
    VERIFY_INDEPENDENTLY = "verify_independently"
    INTEGRATE_SYSTEMS = "integrate_systems"
    OBSERVE_OUTCOMES = "observe_outcomes"
    LEARN_FROM_OUTCOMES = "learn_from_outcomes"
    TEACH_PEERS = "teach_peers"
    RECOVER_AND_RESUME = "recover_and_resume"
    BENCHMARK_COMPARATORS = "benchmark_comparators"
    RUN_RECURSIVE_EXPERIMENTS = "run_recursive_experiments"
    DETECT_METRIC_GAMING = "detect_metric_gaming"
    STOP_DIMINISHING_RETURNS = "stop_diminishing_returns"


REQUIRED_ROLES: tuple[Role, ...] = (
    Role.ORCHESTRATOR,
    Role.EXPLORER,
    Role.ARCHITECT,
    Role.BUILDER,
    Role.CURATOR,
    Role.INTEGRATOR,
    Role.STEWARD,
    Role.OPTIMIZER,
)

REQUIRED_STAGES: tuple[LifecycleStage, ...] = tuple(LifecycleStage)
REQUIRED_CAPABILITIES: tuple[SystemCapability, ...] = tuple(SystemCapability)


@dataclass(frozen=True, slots=True)
class HardenedVisionContract:
    """Machine-checkable product constitution derived from the founding vision."""

    name: str = "Hive Mind OS autonomous product-and-engineering operating system"
    required_roles: tuple[Role, ...] = REQUIRED_ROLES
    required_stages: tuple[LifecycleStage, ...] = REQUIRED_STAGES
    required_capabilities: tuple[SystemCapability, ...] = REQUIRED_CAPABILITIES
    forbidden_shortcuts: tuple[str, ...] = (
        "future_commit_access",
        "self_approval",
        "unsupported_claims",
        "unlicensed_source_copying",
        "silent_source_omission",
        "silent_policy_weakening",
        "silent_test_weakening",
        "concealed_activity",
        "unbounded_self_replication",
        "goal_or_policy_mutation",
        "marketing_only_superiority_claim",
        "live_champion_mutation",
        "single_metric_optimization_without_guardrails",
        "promotion_below_measured_noise",
        "protected_holdout_access",
        "unbounded_recursive_improvement",
        "self_weight_modification",
    )
    source_references: tuple[str, ...] = (
        "user-supplied:founding-prompt",
        "user-supplied:new-team-model-images",
        "user-supplied:mission-control-video",
        "https://github.com/rangerrick337/operator-os/tree/main",
        "https://github.com/nousresearch/hermes-agent",
        "https://www.youtube.com/watch?v=mazBhCg3urw",
        "https://www.youtube.com/watch?v=Gw_hnD7m00M",
        "https://www.youtube.com/watch?v=eaNA2oOXoUg",
        "https://www.youtube.com/watch?v=IbFaY3xFpZM",
        "https://www.youtube.com/watch?v=eA9Zf2-qYYM",
        "https://www.youtube.com/watch?v=kIWMLL0S8X8",
        "https://www.youtube.com/watch?v=t7_ZXgfJVG8",
        "https://github.com/karpathy/autoresearch",
        "https://arxiv.org/abs/2303.16200",
        "https://github.com/agiresearch/AIOS",
        "https://arxiv.org/abs/2407.16741",
        "https://github.com/rivet-dev/agent-os",
        "https://github.com/microsoft/agent-framework",
        "https://arxiv.org/abs/2505.21577",
        "https://github.com/RightNow-AI/openfang",
        "https://github.com/iii-hq/agentos",
    )
    target_unsupervised_routine_work: bool = True
    courtroom_required: bool = True
    source_docket_required: bool = True
    comparative_claims_require_benchmarks: bool = True

    @property
    def fingerprint(self) -> str:
        canonical = "\n".join(
            (
                self.name,
                *(role.value for role in self.required_roles),
                *(stage.value for stage in self.required_stages),
                *(capability.value for capability in self.required_capabilities),
                *self.forbidden_shortcuts,
                *self.source_references,
                str(self.target_unsupervised_routine_work),
                str(self.courtroom_required),
                str(self.source_docket_required),
                str(self.comparative_claims_require_benchmarks),
            )
        )
        return sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class VisionRunEvidence:
    """Evidence proving that a run exercised the complete autonomous lifecycle."""

    contract_fingerprint: str
    completed_roles: tuple[Role, ...]
    completed_stages: tuple[LifecycleStage, ...]
    exercised_capabilities: tuple[SystemCapability, ...]
    evidence_refs: tuple[str, ...]
    actor_variant_ids: tuple[str, ...]
    verifier_variant_ids: tuple[str, ...]
    human_interventions: int = 0
    policy_required_interventions: int = 0
    accessed_future_commits: tuple[str, ...] = ()
    policy_violations: tuple[str, ...] = ()
    rollback_evidence_ref: str | None = None
    provenance_complete: bool = True
    court_case_refs: tuple[str, ...] = ()
    source_docket_audit_ref: str | None = None
    source_inventory_complete: bool = False
    unresolved_source_ids: tuple[str, ...] = ()
    superiority_claimed: bool = False
    comparative_benchmark_ref: str | None = None

    def __post_init__(self) -> None:
        if self.human_interventions < 0 or self.policy_required_interventions < 0:
            raise ValueError("intervention counts cannot be negative")
        if self.policy_required_interventions > self.human_interventions:
            raise ValueError("policy-required interventions cannot exceed total interventions")


@dataclass(frozen=True, slots=True)
class VisionComplianceDecision:
    compliant: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)


class VisionComplianceGate:
    """Fails closed when the founding autonomous-system contract is not proven."""

    def __init__(self, contract: HardenedVisionContract | None = None) -> None:
        self.contract = contract or HardenedVisionContract()

    def evaluate(self, evidence: VisionRunEvidence) -> VisionComplianceDecision:
        reasons: list[str] = []
        if evidence.contract_fingerprint != self.contract.fingerprint:
            reasons.append("vision contract changed")

        missing_roles = set(self.contract.required_roles) - set(evidence.completed_roles)
        if missing_roles:
            reasons.append(
                "missing autonomous roles: " + ", ".join(sorted(role.value for role in missing_roles))
            )

        missing_stages = set(self.contract.required_stages) - set(evidence.completed_stages)
        if missing_stages:
            reasons.append(
                "missing lifecycle stages: "
                + ", ".join(sorted(stage.value for stage in missing_stages))
            )

        missing_capabilities = set(self.contract.required_capabilities) - set(
            evidence.exercised_capabilities
        )
        if missing_capabilities:
            reasons.append(
                "missing autonomous capabilities: "
                + ", ".join(sorted(item.value for item in missing_capabilities))
            )

        if not evidence.evidence_refs:
            reasons.append("run has no evidence references")
        if not evidence.provenance_complete:
            reasons.append("source provenance is incomplete")
        if evidence.accessed_future_commits:
            reasons.append("point-in-time learner accessed target or future commits")
        if evidence.policy_violations:
            reasons.append("run contains policy violations")
        if not evidence.rollback_evidence_ref:
            reasons.append("rollback was not proven")

        if self.contract.courtroom_required and not evidence.court_case_refs:
            reasons.append("courtroom review evidence is missing")
        if self.contract.source_docket_required:
            if not evidence.source_docket_audit_ref:
                reasons.append("source docket audit is missing")
            if not evidence.source_inventory_complete:
                reasons.append("source idea inventory is incomplete")
            if evidence.unresolved_source_ids:
                reasons.append(
                    "required sources remain unresolved: "
                    + ", ".join(sorted(evidence.unresolved_source_ids))
                )
        if (
            self.contract.comparative_claims_require_benchmarks
            and evidence.superiority_claimed
            and not evidence.comparative_benchmark_ref
        ):
            reasons.append("superiority claim lacks comparative benchmark evidence")

        actor_ids = {item for item in evidence.actor_variant_ids if item}
        verifier_ids = {item for item in evidence.verifier_variant_ids if item}
        if not verifier_ids:
            reasons.append("independent verification is missing")
        elif actor_ids & verifier_ids:
            reasons.append("acting agent attempted to approve its own work")

        discretionary_human_work = (
            evidence.human_interventions - evidence.policy_required_interventions
        )
        if self.contract.target_unsupervised_routine_work and discretionary_human_work > 0:
            reasons.append("routine work required human supervision")

        return VisionComplianceDecision(not reasons, tuple(reasons))

    def require(self, evidence: VisionRunEvidence) -> None:
        decision = self.evaluate(evidence)
        if not decision.compliant:
            raise RuntimeError("; ".join(decision.reasons))
