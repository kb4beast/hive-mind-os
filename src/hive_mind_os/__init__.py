"""Hive Mind OS agent kernel."""

from .autonomy import (
    AgentVariant,
    AutonomousMissionLoop,
    AutonomyBudget,
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
from .contracts import (
    ContractValidation,
    load_schema,
    validate_contract,
    validate_runtime_state,
    validate_schema_catalog,
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
    AuditVerificationContext,
    build_audit_verification_context,
    collect_current_state_audit,
    create_audit_artifact,
    verify_audit_artifact,
    write_audit_artifact,
)
from .governed_sources import GovernedSourceAudit, audit_governed_source
from .models import AutonomyLevel, Objective, RiskTier, Role
from .receipts import (
    FileReceiptValidator,
    ReceiptReference,
    ReceiptResult,
    ReceiptValidation,
    ReceiptValidator,
    sha256_digest,
)
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
from .source_docket import (
    FoundingSourceDocket,
    load_default_source_docket,
    load_source_docket,
)
from .vision import HardenedVisionContract, VisionComplianceGate

__all__ = [
    "ActionKind",
    "AgentVariant",
    "AutonomyBudget",
    "AutonomyLevel",
    "AutonomousMissionLoop",
    "AUDITED_BASELINE",
    "AuditVerificationContext",
    "BurdenOfProof",
    "ClassicGptSimulationGate",
    "ClassicGptSourcePack",
    "ClassicGptTurn",
    "ContractValidation",
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
    "GovernedSourceAudit",
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
    "audit_governed_source",
    "build_audit_verification_context",
    "collect_current_state_audit",
    "create_audit_artifact",
    "load_default_source_docket",
    "load_schema",
    "load_source_docket",
    "sha256_digest",
    "validate_contract",
    "validate_runtime_state",
    "validate_schema_catalog",
    "verify_audit_artifact",
    "write_audit_artifact",
]
__version__ = "0.6.0"
