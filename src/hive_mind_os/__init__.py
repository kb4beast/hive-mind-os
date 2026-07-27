"""Hive Mind OS agent kernel."""

from .autonomy import (
    AgentVariant,
    AutonomyBudget,
    AutonomousMissionLoop,
    EvolutionArena,
    MissionCharter,
)
from .classic_gpt import (
    ActionKind,
    ClassicGptSimulationGate,
    ClassicGptSourcePack,
    ClassicGptTurn,
    SimulatedAction,
    SimulationPhase,
)
from .courtroom import (
    BurdenOfProof,
    CourtCase,
    Courtroom,
    CourtVerdict,
    Disposition,
    SourceDocketAuditor,
    SourceRecord,
)
from .current_state_audit import (
    AUDITED_BASELINE,
    collect_current_state_audit,
    create_audit_artifact,
    verify_audit_artifact,
    write_audit_artifact,
)
from .models import AutonomyLevel, Objective, RiskTier, Role
from .recursive_improvement import (
    ExperimentCandidate,
    ExperimentDecision,
    ExperimentEvidence,
    ExperimentVerdict,
    MetricDirection,
    MetricObservation,
    MetricSpec,
    RecursiveImprovementContract,
    RecursiveImprovementController,
    RecursiveImprovementGate,
)
from .repository_learning import RepositoryLearningCurriculum, RepositoryScout
from .receipts import (
    FileReceiptValidator,
    ReceiptReference,
    ReceiptResult,
    ReceiptValidator,
    ReceiptValidation,
    sha256_digest,
)
from .runtime import HiveKernel
from .source_docket import FoundingSourceDocket, load_default_source_docket, load_source_docket
from .vision import HardenedVisionContract, VisionComplianceGate

__all__ = [
    "ActionKind",
    "AgentVariant",
    "AutonomyBudget",
    "AutonomyLevel",
    "AutonomousMissionLoop",
    "AUDITED_BASELINE",
    "BurdenOfProof",
    "ClassicGptSimulationGate",
    "ClassicGptSourcePack",
    "ClassicGptTurn",
    "CourtCase",
    "Courtroom",
    "CourtVerdict",
    "Disposition",
    "EvolutionArena",
    "ExperimentCandidate",
    "ExperimentDecision",
    "ExperimentEvidence",
    "ExperimentVerdict",
    "FoundingSourceDocket",
    "FileReceiptValidator",
    "HardenedVisionContract",
    "HiveKernel",
    "MetricDirection",
    "MetricObservation",
    "MetricSpec",
    "MissionCharter",
    "Objective",
    "RecursiveImprovementContract",
    "RecursiveImprovementController",
    "RecursiveImprovementGate",
    "RepositoryLearningCurriculum",
    "RepositoryScout",
    "ReceiptReference",
    "ReceiptResult",
    "ReceiptValidator",
    "ReceiptValidation",
    "RiskTier",
    "Role",
    "SimulatedAction",
    "SimulationPhase",
    "SourceDocketAuditor",
    "SourceRecord",
    "VisionComplianceGate",
    "collect_current_state_audit",
    "create_audit_artifact",
    "load_default_source_docket",
    "load_source_docket",
    "sha256_digest",
    "verify_audit_artifact",
    "write_audit_artifact",
]
__version__ = "0.5.0"
