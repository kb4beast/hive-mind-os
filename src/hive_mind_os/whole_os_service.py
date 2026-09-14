"""N28 composition root for a configured durable whole-OS campaign."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping, Protocol

from .cortex.repository.mission_bindings import (
    ConfiguredMissionBindingsProvider,
    MissionBindingDescriptor,
    MissionBindingError,
)
from .outcome_graph import (
    OutcomeGraphSpec,
    OutcomeWorkPackage,
    compile_outcome_graph,
    ready_packages,
)
from .scheduler import Job, Scheduler


class ServiceError(RuntimeError):
    pass


class PackageStatus(StrEnum):
    COMPLETED = "completed"
    NO_CHANGE = "no_change"
    BLOCKED_AUTHORITY = "blocked_authority"
    BLOCKED_CAPABILITY = "blocked_capability"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PackageExecutionResult:
    package_id: str
    status: PackageStatus
    candidate_digest: str | None
    evidence_refs: tuple[str, ...]
    message: str = ""

    def __post_init__(self) -> None:
        if not self.package_id.strip() or type(self.status) is not PackageStatus:
            raise ServiceError("package result identity and status must be typed")
        if (
            self.status in {PackageStatus.COMPLETED, PackageStatus.NO_CHANGE}
            and not self.candidate_digest
        ):
            raise ServiceError("successful package results require a candidate digest")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ServiceError("package evidence references must be unique")


class WholeOSHost(Protocol):
    """Host-owned effect boundary; implementations hold credentials and sandboxes."""

    def execute_package(
        self,
        package: OutcomeWorkPackage,
        bindings: tuple[Any, Any],
        payload: Mapping[str, Any],
    ) -> PackageExecutionResult: ...


@dataclass(frozen=True, slots=True)
class WholeOSServiceConfig:
    campaign_id: str
    tenant_id: str
    repository_id: str
    state_dir: Path
    binding_descriptor: MissionBindingDescriptor
    graph: OutcomeGraphSpec
    maximum_attempts: int = 3

    def __post_init__(self) -> None:
        if not self.campaign_id or not self.tenant_id or not self.repository_id:
            raise ServiceError("campaign, tenant, and repository identity are required")
        if (
            self.binding_descriptor.tenant_id != self.tenant_id
            or self.binding_descriptor.repository_id != self.repository_id
        ):
            raise ServiceError("binding descriptor targets another subject")
        if self.maximum_attempts < 1:
            raise ServiceError("maximum attempts must be positive")

    @classmethod
    def from_document(
        cls, document: Mapping[str, object], *, base_dir: Path
    ) -> "WholeOSServiceConfig":
        """Construct configuration from the closed JSON service contract.

        Only inert descriptor and graph data are accepted.  In particular, the
        document has no import paths, commands, callbacks, or credential fields.
        """
        required = {
            "schema_version",
            "campaign_id",
            "tenant_id",
            "repository_id",
            "state_dir",
            "binding_descriptor",
            "graph",
            "maximum_attempts",
        }
        if set(document) != required or document.get("schema_version") != 1:
            raise ServiceError("service configuration has an unknown shape or schema")
        descriptor = document.get("binding_descriptor")
        graph = document.get("graph")
        if not isinstance(descriptor, Mapping) or not isinstance(graph, Mapping):
            raise ServiceError("binding_descriptor and graph must be objects")
        state_value = document["state_dir"]
        if not isinstance(state_value, str) or not state_value:
            raise ServiceError("state_dir must be a non-empty path")
        if not isinstance(document["maximum_attempts"], int) or isinstance(
            document["maximum_attempts"], bool
        ):
            raise ServiceError("maximum_attempts must be an integer")
        try:
            binding = MissionBindingDescriptor.from_document(descriptor)
            graph_spec = graph_from_document(graph)
            return cls(
                str(document["campaign_id"]),
                str(document["tenant_id"]),
                str(document["repository_id"]),
                (base_dir / state_value).resolve(),
                binding,
                graph_spec,
                document["maximum_attempts"],
            )
        except (KeyError, TypeError, ValueError, MissionBindingError) as exc:
            raise ServiceError("service configuration is invalid") from exc


@dataclass(frozen=True, slots=True)
class ServiceObservation:
    campaign_id: str
    status: str
    completed_packages: tuple[str, ...]
    pending_packages: tuple[str, ...]
    blocked_packages: tuple[str, ...]
    last_result: PackageExecutionResult | None = None


class WholeOSService:
    JOB_KIND = "whole-os-package"

    def __init__(
        self,
        config: WholeOSServiceConfig,
        bindings: ConfiguredMissionBindingsProvider,
        host: WholeOSHost,
        *,
        scheduler: Scheduler | None = None,
    ) -> None:
        if bindings.descriptor.digest != config.binding_descriptor.digest:
            raise ServiceError("binding provider differs from configured descriptor")
        self.config = config
        self.bindings = bindings
        self.host = host
        self.scheduler = scheduler or Scheduler(config.state_dir / "queue")
        self.by_id = {package.package_id: package for package in config.graph.packages}
        self._enqueue_ready()

    def _jobs(self) -> tuple[Job, ...]:
        return tuple(
            job
            for job in self.scheduler.jobs()
            if job.kind == self.JOB_KIND and job.mission_id == self.config.campaign_id
        )

    def _completed(self) -> set[str]:
        return {
            str(job.payload["package_id"])
            for job in self._jobs()
            if job.state == "done"
        }

    def _enqueued(self) -> set[str]:
        return {str(job.payload["package_id"]) for job in self._jobs()}

    def _payload(self, package: OutcomeWorkPackage) -> dict[str, object]:
        return {
            "campaign_id": self.config.campaign_id,
            "tenant_id": self.config.tenant_id,
            "repository_id": self.config.repository_id,
            "configuration_digest": self.config.binding_descriptor.digest,
            "graph_digest": self.config.graph.digest,
            "package_id": package.package_id,
            "outcome_ids": list(package.outcome_ids),
            "acceptance_ids": list(package.acceptance_ids),
            "allowed_paths": list(package.allowed_paths),
            "semantic_locks": list(package.semantic_locks),
        }

    def _enqueue_ready(self) -> None:
        completed, enqueued = self._completed(), self._enqueued()
        for package in ready_packages(self.config.graph, completed):
            if package.package_id not in enqueued:
                self.scheduler.enqueue(
                    self.JOB_KIND,
                    self._payload(package),
                    max_attempts=self.config.maximum_attempts,
                    mission_id=self.config.campaign_id,
                )

    def run_once(self) -> ServiceObservation:
        job = self.scheduler.claim(f"whole-os:{self.config.campaign_id}")
        if job is None:
            return self.observe()
        package_id = str(job.payload.get("package_id", ""))
        package = self.by_id.get(package_id)
        if package is None:
            self.scheduler.fail(
                job.id,
                job.lease_token or "",
                "unknown package",
                mission_id=self.config.campaign_id,
            )
            raise ServiceError("queued package is absent from the sealed graph")
        try:
            resolved = self.bindings.resolve(job.payload, self.config.state_dir)
            result = self.host.execute_package(package, resolved, job.payload)
            if result.package_id != package_id:
                raise ServiceError("host returned a cross-package result")
            if result.status in {PackageStatus.COMPLETED, PackageStatus.NO_CHANGE}:
                self.scheduler.complete(
                    job.id, job.lease_token or "", mission_id=self.config.campaign_id
                )
                self._enqueue_ready()
            else:
                self.scheduler.fail(
                    job.id,
                    job.lease_token or "",
                    result.status.value + ": " + result.message,
                    mission_id=self.config.campaign_id,
                )
            return self.observe(last_result=result)
        except Exception as exc:
            self.scheduler.fail(
                job.id,
                job.lease_token or "",
                f"{type(exc).__name__}: {exc}",
                mission_id=self.config.campaign_id,
            )
            return self.observe(
                last_result=PackageExecutionResult(
                    package_id, PackageStatus.FAILED, None, (), str(exc)
                )
            )

    def observe(
        self, *, last_result: PackageExecutionResult | None = None
    ) -> ServiceObservation:
        jobs = self._jobs()
        completed = tuple(
            sorted(
                str(job.payload["package_id"]) for job in jobs if job.state == "done"
            )
        )
        blocked = tuple(
            sorted(
                str(job.payload["package_id"])
                for job in jobs
                if job.state == "dead-letter"
            )
        )
        enqueued = {str(job.payload["package_id"]) for job in jobs}
        pending = tuple(sorted(set(self.by_id) - set(completed)))
        if blocked:
            status = "blocked"
        elif len(completed) == len(self.by_id):
            status = "complete"
        elif any(job.state in {"ready", "leased"} for job in jobs):
            status = "ready"
        elif set(self.by_id) - enqueued:
            status = "dependency_wait"
        else:
            status = "idle"
        return ServiceObservation(
            self.config.campaign_id, status, completed, pending, blocked, last_result
        )

    def close(self) -> None:
        self.scheduler.close()


def graph_from_document(document: Mapping[str, object]) -> OutcomeGraphSpec:
    allowed = {
        "contract_version",
        "base_snapshot",
        "maximum_concurrent",
        "court_receipt",
        "packages",
    }
    if set(document) != allowed or not isinstance(document["packages"], list):
        raise ServiceError("graph document has an unknown shape")
    contract_version = document["contract_version"]
    maximum_concurrent = document["maximum_concurrent"]
    if (
        type(contract_version) is not int
        or type(maximum_concurrent) is not int
    ):
        raise ServiceError("graph contract version and concurrency must be integers")
    packages = []
    for raw in document["packages"]:
        if not isinstance(raw, dict):
            raise ServiceError("graph package must be an object")
        required = {"package_id", "outcome_ids"}
        if (
            not required.issubset(raw)
            or not isinstance(raw["package_id"], str)
            or not isinstance(raw["outcome_ids"], list)
        ):
            raise ServiceError(
                "graph package requires typed package_id and outcome_ids"
            )
        packages.append(
            OutcomeWorkPackage(
                package_id=raw["package_id"],
                outcome_ids=tuple(raw["outcome_ids"]),
                dependencies=tuple(raw.get("dependencies", ())),
                allowed_paths=tuple(raw.get("allowed_paths", ())),
                semantic_locks=tuple(raw.get("semantic_locks", ())),
                acceptance_ids=tuple(raw.get("acceptance_ids", ())),
                risk_tier=str(raw.get("risk_tier", "medium")),
                required_roles=tuple(raw.get("required_roles", ())),
                effort=int(raw.get("effort", 1)),
                rollback=str(raw.get("rollback", "retain prior candidate")),
                state=str(raw.get("state", "pending")),
            )
        )
    return compile_outcome_graph(
        OutcomeGraphSpec(
            packages=tuple(packages),
            base_snapshot=str(document["base_snapshot"]),
            contract_version=contract_version,
            maximum_concurrent=maximum_concurrent,
            court_receipt=str(document["court_receipt"]),
        )
    )


def load_graph(path: str | Path) -> OutcomeGraphSpec:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ServiceError("graph cannot be loaded") from exc
    if not isinstance(value, dict):
        raise ServiceError("graph root must be an object")
    return graph_from_document(value)


def load_service_config(path: str | Path) -> WholeOSServiceConfig:
    """Load and validate an inert service configuration from strict JSON."""
    config_path = Path(path)
    try:
        from .runtime_contracts import strict_json_object

        value = strict_json_object(config_path.read_bytes())
        return WholeOSServiceConfig.from_document(value, base_dir=config_path.parent)
    except ServiceError:
        raise
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise ServiceError("service configuration cannot be loaded") from exc


__all__ = [
    "PackageExecutionResult",
    "PackageStatus",
    "ServiceError",
    "ServiceObservation",
    "WholeOSHost",
    "WholeOSService",
    "WholeOSServiceConfig",
    "graph_from_document",
    "load_graph",
    "load_service_config",
]
