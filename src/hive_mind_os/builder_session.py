"""Bounded builder loop with deterministic path and tool checks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from pathlib import PurePosixPath
from time import monotonic
from typing import Callable, Iterable


class BuilderState(str, Enum):
    READY = "READY"
    WORKING = "WORKING"
    CHECKPOINTED = "CHECKPOINTED"
    TERMINAL = "TERMINAL"


class BuilderDisposition(str, Enum):
    READY_FOR_VERIFICATION = "READY_FOR_VERIFICATION"
    NO_CHANGE = "NO_CHANGE"
    NEEDS_CONTRACT_AMENDMENT = "NEEDS_CONTRACT_AMENDMENT"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class BuilderSessionSpec:
    package_id: str
    attempt_id: str
    tenant_id: str
    starting_candidate: str
    allowed_paths: tuple[str, ...]
    operations: tuple[str, ...] = ("read", "edit", "test")
    acceptance_refs: tuple[str, ...] = ()
    sandbox_profile: str = "isolated"
    model_profile: str = "default"
    max_tools: int = 20
    max_repairs: int = 3
    max_seconds: float = 900


@dataclass(frozen=True, slots=True)
class BuilderSessionResult:
    disposition: BuilderDisposition
    candidate: str | None
    changed_paths: tuple[str, ...]
    checks: tuple[str, ...] = ()
    failures: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()


class BuilderSession:
    def __init__(
        self, spec: BuilderSessionSpec, *, clock: Callable[[], float] | None = None
    ):
        if (
            not spec.package_id
            or not spec.attempt_id
            or spec.max_tools < 1
            or spec.max_repairs < 0
            or spec.max_seconds <= 0
        ):
            raise ValueError("invalid bounded builder session")
        self.spec = spec
        self.clock = clock or monotonic
        self.state = BuilderState.READY
        self.tool_count = 0
        self.repair_count = 0
        self._checkpoint = None
        self.failure_fingerprints = set()

    def record_tool(self, operation: str) -> None:
        if operation not in self.spec.operations:
            raise PermissionError("operation is outside admitted builder capabilities")
        self.tool_count += 1
        if self.tool_count > self.spec.max_tools:
            raise RuntimeError("builder tool budget exhausted")

    def record_failure(self, failure: str) -> bool:
        fp = sha256(failure.encode()).hexdigest()
        if fp in self.failure_fingerprints:
            return False
        self.failure_fingerprints.add(fp)
        self.repair_count += 1
        if self.repair_count > self.spec.max_repairs:
            raise RuntimeError("builder repair budget exhausted")
        return True

    def validate_paths(self, paths: Iterable[str]):
        allowed = tuple(PurePosixPath(p).as_posix() for p in self.spec.allowed_paths)
        for p in paths:
            q = PurePosixPath(p).as_posix()
            if (
                q.startswith("../")
                or q not in allowed
                and not any(q.startswith(a.rstrip("/") + "/") for a in allowed)
            ):
                raise PermissionError(f"path outside builder write scope: {p}")

    def checkpoint(self, candidate: str, changed_paths: Iterable[str]):
        self.validate_paths(changed_paths)
        self._checkpoint = (candidate, tuple(changed_paths))
        self.state = BuilderState.CHECKPOINTED
        return self._checkpoint

    def run(
        self, action: Callable[["BuilderSession"], BuilderSessionResult] | None = None
    ) -> BuilderSessionResult:
        started_at = self.clock()
        self.state = BuilderState.WORKING
        if action:
            result = action(self)
        elif self._checkpoint:
            result = BuilderSessionResult(
                BuilderDisposition.READY_FOR_VERIFICATION,
                self._checkpoint[0],
                self._checkpoint[1],
            )
        else:
            result = BuilderSessionResult(
                BuilderDisposition.NO_CHANGE, self.spec.starting_candidate, ()
            )
        self.validate_paths(result.changed_paths)
        if self.clock() - started_at > self.spec.max_seconds:
            result = BuilderSessionResult(
                BuilderDisposition.BUDGET_EXHAUSTED,
                None,
                (),
                result.checks,
                (*result.failures, "builder wall-time budget exhausted"),
                result.evidence_refs,
            )
        self.state = BuilderState.TERMINAL
        return result
