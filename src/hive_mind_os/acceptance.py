"""Typed, executable acceptance specifications for repository missions."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Mapping, Sequence

from .contracts import validate_contract

CheckOutcome = str
_IDENTIFIER = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")


class AcceptanceSpecificationError(ValueError):
    """An acceptance specification is malformed or ambiguously bound."""


@dataclass(frozen=True, slots=True)
class AcceptanceSpecification:
    """One criterion with the sole command authorized to verify it."""

    identifier: str
    criterion: str
    argv: tuple[str, ...]
    expected: CheckOutcome = "succeeded"

    def __post_init__(self) -> None:
        if _IDENTIFIER.fullmatch(self.identifier) is None:
            raise AcceptanceSpecificationError(
                "acceptance specification identifier must be lowercase kebab-case"
            )
        if not isinstance(self.criterion, str) or not self.criterion.strip():
            raise AcceptanceSpecificationError(
                "acceptance specification criterion is required"
            )
        if len(self.criterion) > 4000:
            raise AcceptanceSpecificationError(
                "acceptance specification criterion exceeds 4000 characters"
            )
        if len(self.argv) > 128:
            raise AcceptanceSpecificationError(
                "acceptance specification argv exceeds 128 arguments"
            )
        if not self.argv or not all(
            isinstance(item, str)
            and item
            and "\x00" not in item
            and len(item) <= 16384
            for item in self.argv
        ):
            raise AcceptanceSpecificationError(
                "acceptance specification argv must contain non-empty strings of at most 16384 characters"
            )
        if self.expected not in {"succeeded", "failed"}:
            raise AcceptanceSpecificationError(
                "acceptance specification expected outcome is invalid"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "id": self.identifier,
            "criterion": self.criterion,
            "command": {
                "argv": list(self.argv),
                "expected": self.expected,
            },
        }

    @property
    def digest(self) -> str:
        encoded = json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return f"sha256:{sha256(encoded).hexdigest()}"

    @classmethod
    def from_dict(cls, document: Mapping[str, object]) -> AcceptanceSpecification:
        validation = validate_contract("acceptance-specification", dict(document))
        if not validation.valid:
            raise AcceptanceSpecificationError("; ".join(validation.issues))
        command = document["command"]
        assert isinstance(command, Mapping)
        argv = command["argv"]
        assert isinstance(argv, list)
        expected = command["expected"]
        assert isinstance(expected, str)
        return cls(
            identifier=str(document["id"]),
            criterion=str(document["criterion"]),
            argv=tuple(str(item) for item in argv),
            expected=expected,
        )


def normalize_acceptance_specifications(
    specifications: Sequence[AcceptanceSpecification | Mapping[str, object]],
) -> tuple[AcceptanceSpecification, ...]:
    """Validate a mission's complete executable acceptance contract."""

    normalized: list[AcceptanceSpecification] = []
    for raw in specifications:
        if isinstance(raw, AcceptanceSpecification):
            specification = raw
        elif isinstance(raw, Mapping):
            specification = AcceptanceSpecification.from_dict(raw)
        else:
            raise AcceptanceSpecificationError(
                "acceptance specifications must be typed objects or contract mappings"
            )
        normalized.append(specification)
    identifiers = [item.identifier for item in normalized]
    if len(identifiers) != len(set(identifiers)):
        raise AcceptanceSpecificationError(
            "acceptance specification identifiers must be unique"
        )
    criteria = [item.criterion for item in normalized]
    if len(criteria) != len(set(criteria)):
        raise AcceptanceSpecificationError(
            "each acceptance criterion requires exactly one specification"
        )
    return tuple(sorted(normalized, key=lambda item: (item.identifier, item.digest)))
