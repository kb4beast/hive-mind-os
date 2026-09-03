"""Installed, subject-neutral public interface for portable DAG operations."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from .dag_executor import (
    DagExecutor,
    ExecutionJournal,
    ExecutionRequest,
    ExecutionSnapshot,
)
from .dag_standard import CompilationReceipt, compile_plan, load_bound_plan
from .portable_plan import PortablePlanBundle, SubjectKind
from .runtime_contracts import canonical_digest


class SubjectExecutionError(RuntimeError):
    """A public operation is unsafe, ambiguous, or unavailable."""


class SubjectExecutionMode(StrEnum):
    REPOSITORY = "repository"
    OFFLINE_LOCAL = "offline-local"
    RESEARCH_ARTIFACT = "research-artifact"
    WORKFLOW = "workflow"


@dataclass(frozen=True, slots=True)
class PlanInspection:
    plan_id: str
    plan_digest: str
    request_id: str
    subject_id: str
    subject_kind: str
    compilation: CompilationReceipt

    def to_document(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "plan_digest": self.plan_digest,
            "request_id": self.request_id,
            "subject_id": self.subject_id,
            "subject_kind": self.subject_kind,
            "compilation": self.compilation.to_document(),
        }


def _absolute_file(path: str | Path, label: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        raise SubjectExecutionError(f"{label} must be an explicit absolute path")
    if not candidate.is_file():
        raise SubjectExecutionError(f"{label} does not exist: {candidate}")
    return candidate


def _bind_mode(plan: PortablePlanBundle, mode: SubjectExecutionMode) -> None:
    if not isinstance(mode, SubjectExecutionMode):
        raise SubjectExecutionError("subject execution mode must be explicit")
    if (
        plan.subject.kind is SubjectKind.REPOSITORY
        and mode is not SubjectExecutionMode.REPOSITORY
    ):
        raise SubjectExecutionError("repository plan requires repository mode")
    if (
        plan.subject.kind is SubjectKind.NON_REPOSITORY
        and mode is SubjectExecutionMode.REPOSITORY
    ):
        raise SubjectExecutionError(
            "non-repository plan requires an explicit non-repository mode"
        )


class SubjectExecutionService:
    """Public facade; construction grants no host or activation authority."""

    def __init__(self, executor: DagExecutor | None = None) -> None:
        self.executor = executor

    def validate_files(
        self,
        *,
        plan_path: str | Path,
        standard_path: str | Path,
        expected_plan_digest: str,
        mode: SubjectExecutionMode,
        expected_request_id: str | None = None,
        expected_subject_id: str | None = None,
    ) -> PlanInspection:
        plan_file = _absolute_file(plan_path, "plan_path")
        standard_file = _absolute_file(standard_path, "standard_path")
        plan_bytes = plan_file.read_bytes()
        standard_bytes = standard_file.read_bytes()
        plan = load_bound_plan(
            plan_bytes,
            expected_plan_digest=expected_plan_digest,
            standard_bytes=standard_bytes,
            expected_request_id=expected_request_id,
            expected_subject_id=expected_subject_id,
        )
        _bind_mode(plan, mode)
        compilation = compile_plan(
            plan_bytes,
            expected_plan_digest=expected_plan_digest,
            standard_bytes=standard_bytes,
            expected_request_id=expected_request_id,
            expected_subject_id=expected_subject_id,
        )
        return PlanInspection(
            plan.plan_id,
            plan.digest(),
            plan.request_id,
            plan.subject.subject_id,
            plan.subject.kind.value,
            compilation,
        )

    def build_file(
        self,
        *,
        plan_path: str | Path,
        standard_path: str | Path,
        expected_plan_digest: str,
        output_path: str | Path,
        mode: SubjectExecutionMode,
        replace_existing: bool = False,
    ) -> PlanInspection:
        inspection = self.validate_files(
            plan_path=plan_path,
            standard_path=standard_path,
            expected_plan_digest=expected_plan_digest,
            mode=mode,
        )
        source = _absolute_file(plan_path, "plan_path")
        target = Path(output_path)
        if not target.is_absolute():
            raise SubjectExecutionError("output_path must be an explicit absolute path")
        if not target.parent.is_dir():
            raise SubjectExecutionError("output parent must already exist")
        if target.is_symlink():
            raise SubjectExecutionError("output_path must not be a symbolic link")
        if target.exists() and not replace_existing:
            raise SubjectExecutionError("output_path already exists")
        plan = PortablePlanBundle.from_bytes(source.read_bytes())
        if plan.digest() != inspection.plan_digest:
            raise SubjectExecutionError("plan_path changed after validation")
        descriptor, temporary_name = tempfile.mkstemp(
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                descriptor = -1
                stream.write(plan.canonical_bytes())
                stream.flush()
                os.fsync(stream.fileno())
            if replace_existing:
                os.replace(temporary, target)
            else:
                try:
                    os.link(temporary, target)
                except FileExistsError as error:
                    raise SubjectExecutionError("output_path already exists") from error
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if temporary.exists():
                temporary.unlink()
        return inspection

    def rounds(self, **arguments: Any) -> tuple[dict[str, Any], ...]:
        inspection = self.validate_files(**arguments)
        return tuple(item.to_document() for item in inspection.compilation.rounds)

    def graph(self, **arguments: Any) -> dict[str, Any]:
        plan_path = arguments["plan_path"]
        inspection = self.validate_files(**arguments)
        plan = PortablePlanBundle.from_bytes(
            _absolute_file(plan_path, "plan_path").read_bytes()
        )
        if plan.digest() != inspection.plan_digest:
            raise SubjectExecutionError("plan_path changed after validation")
        return {
            "plan_id": plan.plan_id,
            "plan_digest": inspection.plan_digest,
            "metrics": inspection.compilation.metrics.to_document(),
            "nodes": [node.node_id for node in plan.nodes],
            "edges": [
                {"from": dependency, "to": node.node_id}
                for node in plan.nodes
                for dependency in node.dependencies
            ],
            "rounds": [item.to_document() for item in inspection.compilation.rounds],
        }

    def execute(self, request: ExecutionRequest) -> ExecutionSnapshot:
        if self.executor is None:
            raise SubjectExecutionError(
                "EXTERNAL_RUNTIME_REQUIRED: configure an authenticated host runtime"
            )
        return self.executor.execute(request)

    resume = execute

    def cancel(self, request: ExecutionRequest, *, reason: str) -> ExecutionSnapshot:
        if self.executor is None:
            raise SubjectExecutionError(
                "EXTERNAL_RUNTIME_REQUIRED: configure an authenticated host runtime"
            )
        return self.executor.cancel(request, reason=reason)

    @staticmethod
    def status(
        *,
        state_path: str | Path,
        plan_path: str | Path,
        expected_plan_digest: str,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        plan_file = _absolute_file(plan_path, "plan_path")
        plan = PortablePlanBundle.from_bytes(plan_file.read_bytes())
        if plan.digest() != expected_plan_digest:
            raise SubjectExecutionError("status plan digest does not match expected bytes")
        binding = {
            "plan_digest": plan.digest(),
            "subject_id": plan.subject.subject_id,
        }
        path = Path(state_path)
        if not path.is_absolute():
            raise SubjectExecutionError("state_path must be an explicit absolute path")
        if not path.exists():
            return {
                "state_path": str(path),
                "binding": binding,
                "runs": [],
                "state_present": False,
            }
        if not path.is_file():
            raise SubjectExecutionError("state_path must name the execution database")
        with ExecutionJournal(path, read_only=True) as journal:
            run_ids = journal.run_ids() if run_id is None else (run_id,)
            snapshots = []
            for candidate in run_ids:
                snapshot = journal.snapshot(candidate)
                if snapshot is not None:
                    if (
                        snapshot.plan_digest != binding["plan_digest"]
                        or snapshot.subject_id != binding["subject_id"]
                    ):
                        if run_id is not None:
                            raise SubjectExecutionError(
                                "requested run belongs to another plan or subject"
                            )
                        continue
                    snapshots.append(snapshot.to_document())
        return {
            "state_path": str(path),
            "binding": binding,
            "runs": snapshots,
            "state_present": True,
        }

    @staticmethod
    def graph_identity(graph: dict[str, Any]) -> str:
        return canonical_digest(graph)


__all__ = [
    "PlanInspection",
    "SubjectExecutionError",
    "SubjectExecutionMode",
    "SubjectExecutionService",
]
