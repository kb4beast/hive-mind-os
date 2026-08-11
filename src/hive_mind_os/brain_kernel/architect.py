"""Fail-closed architecture artifacts for the canonical Hive Cortex.

Architects may propose a design, but cannot approve implementation or cause an
effect.  This module keeps the proposal useful to downstream Builder and
Curator roles by requiring explicit alternatives, operational tradeoffs, and a
complete mapping from sealed acceptance criteria to both design and
verification evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from .canonical import canonical_digest


class ArchitectureValidationError(ValueError):
    """An architecture proposal is incomplete, ambiguous, or unsafe to hand off."""


def _required(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ArchitectureValidationError(f"{label} is required")
    return value.strip()


def _items(values: Sequence[str], label: str, *, minimum: int = 1) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ArchitectureValidationError(f"{label} must be a sequence of strings")
    normalized = tuple(_required(value, label) for value in values)
    if len(normalized) < minimum:
        raise ArchitectureValidationError(f"{label} requires at least {minimum} item(s)")
    if len(set(normalized)) != len(normalized):
        raise ArchitectureValidationError(f"{label} must not contain duplicates")
    return normalized


@dataclass(frozen=True, slots=True)
class DesignOption:
    """One viable design alternative and the costs it accepts."""

    identifier: str
    summary: str
    tradeoffs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "identifier", _required(self.identifier, "option identifier"))
        object.__setattr__(self, "summary", _required(self.summary, "option summary"))
        object.__setattr__(self, "tradeoffs", _items(self.tradeoffs, "option tradeoffs"))

    def to_document(self) -> dict[str, object]:
        return {
            "identifier": self.identifier,
            "summary": self.summary,
            "tradeoffs": list(self.tradeoffs),
        }


@dataclass(frozen=True, slots=True)
class InterfaceContract:
    """A stable boundary that the selected design must preserve or migrate."""

    identifier: str
    provider: str
    consumer: str
    contract: str
    compatibility: str

    def __post_init__(self) -> None:
        for label in ("identifier", "provider", "consumer", "contract", "compatibility"):
            object.__setattr__(self, label, _required(getattr(self, label), f"interface {label}"))

    def to_document(self) -> dict[str, str]:
        return {
            "identifier": self.identifier,
            "provider": self.provider,
            "consumer": self.consumer,
            "contract": self.contract,
            "compatibility": self.compatibility,
        }


@dataclass(frozen=True, slots=True)
class AcceptanceMapping:
    """Bind one sealed criterion to design elements and independent checks."""

    criterion_id: str
    design_refs: tuple[str, ...]
    verification_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "criterion_id", _required(self.criterion_id, "criterion id"))
        object.__setattr__(self, "design_refs", _items(self.design_refs, "acceptance design references"))
        object.__setattr__(self, "verification_refs", _items(self.verification_refs, "acceptance verification references"))

    def to_document(self) -> dict[str, object]:
        return {
            "criterion_id": self.criterion_id,
            "design_refs": list(self.design_refs),
            "verification_refs": list(self.verification_refs),
        }


@dataclass(frozen=True, slots=True)
class ArchitectureArtifact:
    """An effect-free, evidence-bound Architect handoff artifact."""

    objective: str
    options: tuple[DesignOption, ...]
    selected_option: str
    interfaces: tuple[InterfaceContract, ...]
    invariants: tuple[str, ...]
    threats: tuple[str, ...]
    data_classification: tuple[str, ...]
    compatibility_impact: str
    migration_plan: str
    rollback_plan: str
    acceptance_mappings: tuple[AcceptanceMapping, ...]
    unknowns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "objective", _required(self.objective, "objective"))
        if len(self.options) < 2:
            raise ArchitectureValidationError("architecture requires at least two options")
        if any(not isinstance(option, DesignOption) for option in self.options):
            raise ArchitectureValidationError("options must be DesignOption values")
        option_ids = tuple(option.identifier for option in self.options)
        if len(set(option_ids)) != len(option_ids):
            raise ArchitectureValidationError("option identifiers must be unique")
        object.__setattr__(self, "selected_option", _required(self.selected_option, "selected option"))
        if self.selected_option not in option_ids:
            raise ArchitectureValidationError("selected option must name a proposed option")
        if not self.interfaces or any(not isinstance(item, InterfaceContract) for item in self.interfaces):
            raise ArchitectureValidationError("architecture requires interface contracts")
        interface_ids = tuple(item.identifier for item in self.interfaces)
        if len(set(interface_ids)) != len(interface_ids):
            raise ArchitectureValidationError("interface identifiers must be unique")
        object.__setattr__(self, "invariants", _items(self.invariants, "invariants"))
        object.__setattr__(self, "threats", _items(self.threats, "threats"))
        object.__setattr__(self, "data_classification", _items(self.data_classification, "data classification"))
        for label in ("compatibility_impact", "migration_plan", "rollback_plan"):
            object.__setattr__(self, label, _required(getattr(self, label), label.replace("_", " ")))
        if any(not isinstance(item, AcceptanceMapping) for item in self.acceptance_mappings):
            raise ArchitectureValidationError("acceptance mappings must be AcceptanceMapping values")
        mapping_ids = tuple(item.criterion_id for item in self.acceptance_mappings)
        if len(set(mapping_ids)) != len(mapping_ids):
            raise ArchitectureValidationError("acceptance mappings must have unique criterion ids")
        object.__setattr__(self, "unknowns", _items(self.unknowns, "unknowns", minimum=0))

    def validate_against(self, sealed_criteria: Iterable[str]) -> None:
        """Require exact, non-optional coverage of the sealed acceptance set."""

        criteria = _items(tuple(sealed_criteria), "sealed criteria")
        mapped = tuple(mapping.criterion_id for mapping in self.acceptance_mappings)
        if set(mapped) != set(criteria):
            missing = sorted(set(criteria) - set(mapped))
            extra = sorted(set(mapped) - set(criteria))
            details = []
            if missing:
                details.append("missing: " + ", ".join(missing))
            if extra:
                details.append("unknown: " + ", ".join(extra))
            raise ArchitectureValidationError("acceptance mappings must exactly cover sealed criteria (" + "; ".join(details) + ")")

    def to_document(self) -> dict[str, object]:
        return {
            "objective": self.objective,
            "options": [option.to_document() for option in self.options],
            "selected_option": self.selected_option,
            "interfaces": [interface.to_document() for interface in self.interfaces],
            "invariants": list(self.invariants),
            "threats": list(self.threats),
            "data_classification": list(self.data_classification),
            "compatibility_impact": self.compatibility_impact,
            "migration_plan": self.migration_plan,
            "rollback_plan": self.rollback_plan,
            "acceptance_mappings": [mapping.to_document() for mapping in self.acceptance_mappings],
            "unknowns": list(self.unknowns),
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_document())


class Architect:
    """Validate a proposed architecture before it can be handed to another role."""

    def produce(self, artifact: ArchitectureArtifact, *, sealed_criteria: Iterable[str]) -> ArchitectureArtifact:
        if not isinstance(artifact, ArchitectureArtifact):
            raise ArchitectureValidationError("architect requires an ArchitectureArtifact")
        artifact.validate_against(sealed_criteria)
        return artifact
