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
from .runtime import HiveKernel
from .source_docket import FoundingSourceDocket, load_default_source_docket, load_source_docket
from .vision import HardenedVisionContract, VisionComplianceGate

__all__ = [
    "ActionKind",
    "AgentVariant",
    "AutonomyBudget",
    "AutonomyLevel",
    "AutonomousMissionLoop",
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
    "RiskTier",
    "Role",
    "SimulatedAction",
    "SimulationPhase",
    "SourceDocketAuditor",
    "SourceRecord",
    "VisionComplianceGate",
    "load_default_source_docket",
    "load_source_docket",
]
__version__ = "0.5.0"
