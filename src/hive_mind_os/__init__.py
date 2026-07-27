"""Hive Mind OS agent kernel."""

from .autonomy import (
    AgentVariant,
    AutonomyBudget,
    AutonomousMissionLoop,
    EvolutionArena,
    MissionCharter,
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
from .repository_learning import RepositoryLearningCurriculum, RepositoryScout
from .runtime import HiveKernel
from .source_docket import FoundingSourceDocket, load_default_source_docket, load_source_docket
from .vision import HardenedVisionContract, VisionComplianceGate

__all__ = [
    "AgentVariant",
    "AutonomyBudget",
    "AutonomyLevel",
    "AutonomousMissionLoop",
    "BurdenOfProof",
    "CourtCase",
    "Courtroom",
    "CourtVerdict",
    "Disposition",
    "EvolutionArena",
    "FoundingSourceDocket",
    "HardenedVisionContract",
    "HiveKernel",
    "MissionCharter",
    "Objective",
    "RepositoryLearningCurriculum",
    "RepositoryScout",
    "RiskTier",
    "Role",
    "SourceDocketAuditor",
    "SourceRecord",
    "VisionComplianceGate",
    "load_default_source_docket",
    "load_source_docket",
]
__version__ = "0.3.0"
