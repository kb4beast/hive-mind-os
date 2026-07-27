"""Hive Mind OS agent kernel."""

from .autonomy import (
    AgentVariant,
    AutonomyBudget,
    AutonomousMissionLoop,
    EvolutionArena,
    MissionCharter,
)
from .models import AutonomyLevel, Objective, RiskTier, Role
from .repository_learning import RepositoryLearningCurriculum, RepositoryScout
from .runtime import HiveKernel
from .vision import HardenedVisionContract, VisionComplianceGate

__all__ = [
    "AgentVariant",
    "AutonomyBudget",
    "AutonomyLevel",
    "AutonomousMissionLoop",
    "EvolutionArena",
    "HardenedVisionContract",
    "HiveKernel",
    "MissionCharter",
    "Objective",
    "RepositoryLearningCurriculum",
    "RepositoryScout",
    "RiskTier",
    "Role",
    "VisionComplianceGate",
]
__version__ = "0.3.0"
