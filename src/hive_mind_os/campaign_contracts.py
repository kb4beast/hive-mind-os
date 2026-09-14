"""Closed, inert campaign mission and work-package contracts (N04).

These records are planning/evidence bindings only.  They neither issue authority
nor execute a worker.  They deliberately reuse the portable runtime validators so
the boundary is stable across hosts and JSON readers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

from .runtime_contracts import (
    ContractViolation,
    canonical_digest,
    portable_path,
    require_digest,
    require_identifier,
    require_time,
    strict_json_object,
)

_SHA = re.compile(r"[0-9a-f]{40}\Z")


class CampaignContractErrorCode(StrEnum):
    INVALID = "N04-INVALID"
    UNKNOWN_FIELD = "N04-UNKNOWN-FIELD"
    UNKNOWN_STATE = "N04-UNKNOWN-STATE"
    ORPHAN_REQUIREMENT = "N04-ORPHAN-REQUIREMENT"
    ORPHAN_DEPENDENCY = "N04-ORPHAN-DEPENDENCY"
    AUTHORITY_CHANGED = "N04-AUTHORITY-CHANGED"
    RECEIPT_INCONSISTENT = "N04-RECEIPT-INCONSISTENT"
    HISTORICAL_NOT_ALLOWED = "N04-HISTORICAL-NOT-ALLOWED"


# Stable machine-readable vocabulary for downstream N08–N27 adapters.
ERROR_CODES = tuple(item.value for item in CampaignContractErrorCode)


def _fail(code: CampaignContractErrorCode, message: str) -> None:
    raise ContractViolation(f"{code.value}: {message}")


def _nonempty(value: str, label: str) -> None:
    if type(value) is not str or not value.strip():
        _fail(CampaignContractErrorCode.INVALID, f"{label} is required")


def _ids(values: tuple[str, ...], label: str) -> None:
    if type(values) is not tuple or not values or len(values) != len(set(values)):
        _fail(CampaignContractErrorCode.INVALID, f"{label} must be non-empty and unique")
    for value in values:
        try:
            require_identifier(value, label)
        except ContractViolation as error:
            _fail(CampaignContractErrorCode.INVALID, str(error))


def _sha(value: str, label: str) -> None:
    if type(value) is not str or _SHA.fullmatch(value) is None:
        _fail(CampaignContractErrorCode.INVALID, f"{label} must be a lowercase 40-hex SHA")


class ClaimLevel(StrEnum):
    STATIC = "static"
    RUNTIME = "runtime"
    PRODUCTION_CANDIDATE = "production-candidate"
    DEPLOYED_OBSERVED = "deployed-observed"


class CampaignState(StrEnum):
    DRAFT = "DRAFT"
    READY = "READY"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    NO_CHANGE = "NO_CHANGE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class PackageState(StrEnum):
    PROPOSED = "PROPOSED"
    READY = "READY"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    NO_CHANGE = "NO_CHANGE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"


def campaign_state_event(state: CampaignState) -> str:
    """Map only known N04 states to existing kernel event vocabulary."""
    if not isinstance(state, CampaignState):
        _fail(CampaignContractErrorCode.UNKNOWN_STATE, "campaign state is unknown")
    return {
        CampaignState.DRAFT: "MISSION_CREATED",
        CampaignState.READY: "MISSION_READY",
        CampaignState.RUNNING: "MISSION_STARTED",
        CampaignState.VERIFYING: "MISSION_VERIFYING",
        CampaignState.COMPLETED: "MISSION_COMPLETED",
        CampaignState.NO_CHANGE: "MISSION_COMPLETED",
        CampaignState.FAILED: "MISSION_FAILED",
        CampaignState.CANCELLED: "MISSION_CANCELLED",
    }[state]


def package_state_event(state: PackageState) -> str:
    if not isinstance(state, PackageState):
        _fail(CampaignContractErrorCode.UNKNOWN_STATE, "package state is unknown")
    return {
        PackageState.PROPOSED: "WORK_PROPOSED", PackageState.READY: "WORK_READY",
        PackageState.RUNNING: "WORK_STARTED", PackageState.VERIFYING: "WORK_VERIFYING",
        PackageState.COMPLETED: "WORK_COMPLETED", PackageState.NO_CHANGE: "WORK_COMPLETED",
        PackageState.FAILED: "WORK_FAILED", PackageState.CANCELLED: "WORK_CANCELLED",
        PackageState.SUPERSEDED: "WORK_SUPERSEDED",
    }[state]


@dataclass(frozen=True, slots=True)
class ResourceAllocation:
    max_wall_seconds: int
    max_model_calls: int
    max_cost_microunits: int

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                _fail(CampaignContractErrorCode.INVALID, f"{name} must be a non-negative integer")

    def to_document(self) -> dict[str, int]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class AcceptanceBinding:
    acceptance_id: str
    capability: str
    artifact_ref: str
    result: str
    owner: str
    claim_level: ClaimLevel

    def __post_init__(self) -> None:
        for value, label in ((self.acceptance_id, "acceptance_id"), (self.capability, "capability"), (self.owner, "owner")):
            try:
                require_identifier(value, label)
            except ContractViolation as error:
                _fail(CampaignContractErrorCode.INVALID, str(error))
        _nonempty(self.artifact_ref, "artifact_ref")
        _nonempty(self.result, "result")
        if not isinstance(self.claim_level, ClaimLevel):
            _fail(CampaignContractErrorCode.INVALID, "claim_level is unknown")

    def to_document(self) -> dict[str, str]:
        return {"acceptance_id": self.acceptance_id, "capability": self.capability,
                "artifact_ref": self.artifact_ref, "result": self.result,
                "owner": self.owner, "claim_level": self.claim_level.value}


@dataclass(frozen=True, slots=True)
class CandidateCompletion:
    disposition: str
    commit_sha: str
    tree_digest: str
    output_receipt_digests: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.disposition not in {"implemented", "no-change"}:
            _fail(CampaignContractErrorCode.INVALID, "completion disposition is unknown")
        _sha(self.commit_sha, "commit_sha")
        try:
            require_digest(self.tree_digest, "tree_digest")
        except ContractViolation as error:
            _fail(CampaignContractErrorCode.INVALID, str(error))
        if (type(self.output_receipt_digests) is not tuple or not self.output_receipt_digests
                or len(self.output_receipt_digests) != len(set(self.output_receipt_digests))):
            _fail(CampaignContractErrorCode.INVALID, "output_receipt_digests must be non-empty and unique")
        for digest in self.output_receipt_digests:
            try:
                require_digest(digest, "output receipt digest")
            except ContractViolation as error:
                _fail(CampaignContractErrorCode.INVALID, str(error))

    def to_document(self) -> dict[str, Any]:
        return {"disposition": self.disposition, "commit_sha": self.commit_sha,
                "tree_digest": self.tree_digest, "output_receipt_digests": list(self.output_receipt_digests)}


@dataclass(frozen=True, slots=True)
class WorkPackage:
    """C03: one bounded outcome package and all its exact completion evidence."""
    schema_version: int
    package_id: str
    mission_id: str
    objective: str
    target_boundary: str
    requirement_ids: tuple[str, ...]
    dependencies: tuple[str, ...]
    acceptance: tuple[AcceptanceBinding, ...]
    risk: str
    resources: ResourceAllocation
    outputs: tuple[str, ...]
    rollback: str
    authority_digest: str
    state: PackageState
    created_at: str
    completion: CandidateCompletion | None = None

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            _fail(CampaignContractErrorCode.INVALID, "unsupported work package schema version")
        for value, label in ((self.package_id, "package_id"), (self.mission_id, "mission_id")):
            try: require_identifier(value, label)
            except ContractViolation as error: _fail(CampaignContractErrorCode.INVALID, str(error))
        _nonempty(self.objective, "objective")
        try: portable_path(self.target_boundary)
        except ContractViolation as error: _fail(CampaignContractErrorCode.INVALID, str(error))
        _ids(self.requirement_ids, "requirement_ids")
        if type(self.dependencies) is not tuple or len(self.dependencies) != len(set(self.dependencies)):
            _fail(CampaignContractErrorCode.INVALID, "dependencies must be unique")
        for value in self.dependencies:
            try: require_identifier(value, "dependency")
            except ContractViolation as error: _fail(CampaignContractErrorCode.INVALID, str(error))
        if self.package_id in self.dependencies:
            _fail(CampaignContractErrorCode.ORPHAN_DEPENDENCY, "package cannot depend on itself")
        if type(self.acceptance) is not tuple or not self.acceptance or len({item.acceptance_id for item in self.acceptance}) != len(self.acceptance):
            _fail(CampaignContractErrorCode.INVALID, "acceptance must be non-empty with unique IDs")
        _nonempty(self.risk, "risk"); _ids(self.outputs, "outputs"); _nonempty(self.rollback, "rollback")
        try: require_digest(self.authority_digest, "authority_digest"); require_time(self.created_at, "created_at")
        except ContractViolation as error: _fail(CampaignContractErrorCode.INVALID, str(error))
        if not isinstance(self.state, PackageState): _fail(CampaignContractErrorCode.UNKNOWN_STATE, "package state is unknown")
        if self.state in {PackageState.COMPLETED, PackageState.NO_CHANGE} and self.completion is None:
            _fail(CampaignContractErrorCode.RECEIPT_INCONSISTENT, "terminal package requires completion")
        if self.completion is not None and ((self.state is PackageState.NO_CHANGE) != (self.completion.disposition == "no-change")):
            _fail(CampaignContractErrorCode.RECEIPT_INCONSISTENT, "state and completion disposition disagree")

    def to_document(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "package_id": self.package_id, "mission_id": self.mission_id,
          "objective": self.objective, "target_boundary": self.target_boundary, "requirement_ids": list(self.requirement_ids),
          "dependencies": list(self.dependencies), "acceptance": [x.to_document() for x in self.acceptance], "risk": self.risk,
          "resources": self.resources.to_document(), "outputs": list(self.outputs), "rollback": self.rollback,
          "authority_digest": self.authority_digest, "state": self.state.value, "created_at": self.created_at,
          "completion": None if self.completion is None else self.completion.to_document()}

    @property
    def digest(self) -> str: return canonical_digest(self.to_document())


@dataclass(frozen=True, slots=True)
class CampaignMission:
    """C02: immutable campaign mission binding its packages and requirements."""
    schema_version: int
    mission_id: str
    objective: str
    target_boundary: str
    requirement_ids: tuple[str, ...]
    packages: tuple[WorkPackage, ...]
    authority_digest: str
    state: CampaignState
    created_at: str
    parent_digest: str | None = None

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1: _fail(CampaignContractErrorCode.INVALID, "unsupported campaign schema version")
        try: require_identifier(self.mission_id, "mission_id"); portable_path(self.target_boundary); require_digest(self.authority_digest, "authority_digest"); require_time(self.created_at, "created_at")
        except ContractViolation as error: _fail(CampaignContractErrorCode.INVALID, str(error))
        _nonempty(self.objective, "objective"); _ids(self.requirement_ids, "requirement_ids")
        if type(self.packages) is not tuple or not self.packages or len({item.package_id for item in self.packages}) != len(self.packages): _fail(CampaignContractErrorCode.INVALID, "packages must be non-empty and unique")
        package_ids = {item.package_id for item in self.packages}
        if any(item.mission_id != self.mission_id for item in self.packages): _fail(CampaignContractErrorCode.INVALID, "package belongs to another mission")
        if any(item.authority_digest != self.authority_digest for item in self.packages): _fail(CampaignContractErrorCode.AUTHORITY_CHANGED, "package authority differs from mission")
        if any(not set(item.requirement_ids).issubset(self.requirement_ids) for item in self.packages): _fail(CampaignContractErrorCode.ORPHAN_REQUIREMENT, "package references undeclared requirement")
        if any(not set(item.dependencies).issubset(package_ids) for item in self.packages): _fail(CampaignContractErrorCode.ORPHAN_DEPENDENCY, "package dependency is undeclared")
        if not isinstance(self.state, CampaignState): _fail(CampaignContractErrorCode.UNKNOWN_STATE, "mission state is unknown")
        if self.parent_digest is not None:
            try: require_digest(self.parent_digest, "parent_digest")
            except ContractViolation as error: _fail(CampaignContractErrorCode.INVALID, str(error))

    def to_document(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "mission_id": self.mission_id, "objective": self.objective,
          "target_boundary": self.target_boundary, "requirement_ids": list(self.requirement_ids),
          "packages": [x.to_document() for x in self.packages], "authority_digest": self.authority_digest,
          "state": self.state.value, "created_at": self.created_at, "parent_digest": self.parent_digest}

    @property
    def digest(self) -> str: return canonical_digest(self.to_document())


@dataclass(frozen=True, slots=True)
class SuccessorContract:
    """C09: append-only successor binding; acceptance changes need a disposition."""
    predecessor_digest: str
    successor: CampaignMission
    inherited_requirement_ids: tuple[str, ...]
    changed_acceptance_ids: tuple[str, ...]
    independent_disposition_digest: str | None

    def __post_init__(self) -> None:
        try: require_digest(self.predecessor_digest, "predecessor_digest")
        except ContractViolation as error: _fail(CampaignContractErrorCode.INVALID, str(error))
        _ids(self.inherited_requirement_ids, "inherited_requirement_ids")
        if self.successor.parent_digest != self.predecessor_digest:
            _fail(CampaignContractErrorCode.INVALID, "successor must retain predecessor digest")
        if set(self.inherited_requirement_ids) != set(self.successor.requirement_ids): _fail(CampaignContractErrorCode.ORPHAN_REQUIREMENT, "successor must retain every requirement")
        if type(self.changed_acceptance_ids) is not tuple or len(self.changed_acceptance_ids) != len(set(self.changed_acceptance_ids)): _fail(CampaignContractErrorCode.INVALID, "changed acceptance IDs must be unique")
        if self.changed_acceptance_ids and self.independent_disposition_digest is None: _fail(CampaignContractErrorCode.INVALID, "changed acceptance requires independent disposition")
        acceptance_ids = {item.acceptance_id for package in self.successor.packages for item in package.acceptance}
        if not set(self.changed_acceptance_ids).issubset(acceptance_ids):
            _fail(CampaignContractErrorCode.INVALID, "changed acceptance is not in successor")
        if self.independent_disposition_digest is not None:
            try: require_digest(self.independent_disposition_digest, "independent_disposition_digest")
            except ContractViolation as error: _fail(CampaignContractErrorCode.INVALID, str(error))

    def to_document(self) -> dict[str, Any]:
        return {"predecessor_digest": self.predecessor_digest,
                "successor": self.successor.to_document(),
                "inherited_requirement_ids": list(self.inherited_requirement_ids),
                "changed_acceptance_ids": list(self.changed_acceptance_ids),
                "independent_disposition_digest": self.independent_disposition_digest}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_document())


def parse_campaign_mission(raw: bytes, *, fixture_mode: bool = False) -> CampaignMission:
    """Parse only current production schema; historical input is fixture-only."""
    document = strict_json_object(raw)
    if document.get("schema_version") != 1:
        if fixture_mode and document.get("historical_inert_plan") is True:
            _fail(CampaignContractErrorCode.HISTORICAL_NOT_ALLOWED, "historical inert plans are not C02 records")
        _fail(CampaignContractErrorCode.HISTORICAL_NOT_ALLOWED, "unsupported campaign schema version")
    allowed = {"schema_version", "mission_id", "objective", "target_boundary", "requirement_ids", "packages", "authority_digest", "state", "created_at", "parent_digest"}
    if set(document) - allowed: _fail(CampaignContractErrorCode.UNKNOWN_FIELD, "unknown campaign field")
    packages = tuple(_package_from_document(item) for item in document.get("packages", ()))
    return CampaignMission(document["schema_version"], document["mission_id"], document["objective"], document["target_boundary"], tuple(document["requirement_ids"]), packages, document["authority_digest"], CampaignState(document["state"]), document["created_at"], document.get("parent_digest"))


def _package_from_document(value: Any) -> WorkPackage:
    if not isinstance(value, Mapping): _fail(CampaignContractErrorCode.INVALID, "package must be an object")
    allowed = {"schema_version", "package_id", "mission_id", "objective", "target_boundary", "requirement_ids", "dependencies", "acceptance", "risk", "resources", "outputs", "rollback", "authority_digest", "state", "created_at", "completion"}
    if set(value) - allowed:
        _fail(CampaignContractErrorCode.UNKNOWN_FIELD, "unknown work package field")
    completion = value.get("completion")
    if completion is not None and (not isinstance(completion, Mapping) or set(completion) != {"disposition", "commit_sha", "tree_digest", "output_receipt_digests"}):
        _fail(CampaignContractErrorCode.UNKNOWN_FIELD, "invalid completion fields")
    parsed_completion = None if completion is None else CandidateCompletion(completion["disposition"], completion["commit_sha"], completion["tree_digest"], tuple(completion["output_receipt_digests"]))
    acceptance = []
    for item in value["acceptance"]:
        if not isinstance(item, Mapping) or set(item) != {"acceptance_id", "capability", "artifact_ref", "result", "owner", "claim_level"}:
            _fail(CampaignContractErrorCode.UNKNOWN_FIELD, "invalid acceptance fields")
        acceptance.append(AcceptanceBinding(item["acceptance_id"], item["capability"], item["artifact_ref"], item["result"], item["owner"], ClaimLevel(item["claim_level"])))
    resources = value["resources"]
    if not isinstance(resources, Mapping) or set(resources) != {"max_wall_seconds", "max_model_calls", "max_cost_microunits"}:
        _fail(CampaignContractErrorCode.UNKNOWN_FIELD, "invalid resource fields")
    return WorkPackage(value["schema_version"], value["package_id"], value["mission_id"], value["objective"], value["target_boundary"], tuple(value["requirement_ids"]), tuple(value["dependencies"]), tuple(acceptance), value["risk"], ResourceAllocation(**resources), tuple(value["outputs"]), value["rollback"], value["authority_digest"], PackageState(value["state"]), value["created_at"], parsed_completion)


def parse_historical_inert_plan(raw: bytes, *, fixture_mode: bool = False) -> Mapping[str, Any]:
    """Read a declared historical fixture only; it can never enter C02 admission."""
    if not fixture_mode:
        _fail(CampaignContractErrorCode.HISTORICAL_NOT_ALLOWED, "historical plan requires fixture_mode")
    document = strict_json_object(raw)
    if document.get("historical_inert_plan") is not True or type(document.get("schema_version")) is not int:
        _fail(CampaignContractErrorCode.HISTORICAL_NOT_ALLOWED, "not a declared historical inert plan")
    return document
