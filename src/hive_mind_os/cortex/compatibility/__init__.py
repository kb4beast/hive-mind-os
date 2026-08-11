"""Compatibility firewall for legacy runtime entry points."""

from .adapters import (
    AutonomousBrainAdapter,
    CompatibilityRegistry,
    LegacyAdapter,
    LegacyWorkerAdapter,
    MissionLoopAdapter,
    RepositoryMissionAdapter,
    default_compatibility_registry,
)
from .models import (
    AdapterDescriptor,
    AdapterMode,
    AuthorityPath,
    CompatibilityError,
    CompatibilityObservation,
    CompatibilityRequest,
    RetirementBlocker,
)
from .parity import ParityProbe, ParityVerdict
from .routing import RollbackRouter, RouteDecision

__all__ = (
    "AdapterDescriptor",
    "AdapterMode",
    "AuthorityPath",
    "AutonomousBrainAdapter",
    "CompatibilityError",
    "CompatibilityObservation",
    "CompatibilityRegistry",
    "CompatibilityRequest",
    "LegacyAdapter",
    "LegacyWorkerAdapter",
    "MissionLoopAdapter",
    "ParityProbe",
    "ParityVerdict",
    "RepositoryMissionAdapter",
    "RetirementBlocker",
    "RollbackRouter",
    "RouteDecision",
    "default_compatibility_registry",
)
