"""N28 composition root for a configured durable whole-OS campaign."""

from __future__ import annotations

import json
import os
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from threading import Event, Lock, Thread
from types import MappingProxyType
from typing import Any, Callable, Iterator, Mapping, Protocol
from uuid import uuid4

from .cohort_assurance import (
    TerminalAssessment,
    TerminalEvidence,
    convergence_candidate_digest,
)
from .cohort_runtime import ConvergenceResult, VerificationResult
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
from .receipts import filesystem_path
from .runtime_contracts import canonical_digest
from .scheduler import Job, Scheduler, StaleLeaseError


class ServiceError(RuntimeError):
    pass


class _RetainedScope:
    """Verdict memo for exactly one public invocation; dead once it exits."""

    __slots__ = ("open", "verdicts")

    def __init__(self) -> None:
        self.open = True
        self.verdicts: dict[str, str | None] = {}


# The scope of the public invocation running in this execution context, keyed by
# service identity.  It is only an efficiency memo for *private* helpers: every public
# entry replaces it unconditionally (``WholeOSService._invocation``), and a scope that
# has exited is closed, so a copied or inherited context can never authorize a call.
_RETAINED_SCOPES: ContextVar[dict[int, _RetainedScope] | None] = ContextVar(
    "whole_os_retained_scopes", default=None
)


class _LeaseHeartbeats:
    """Keep claimed jobs live through host calls and durable result writes.

    A coordinator can be descheduled while a worker is running or while an fsync is
    in progress.  Heartbeating on a dedicated thread prevents those pauses from
    turning a completed effect into a stale lease.  Per-job transition locks keep
    the last heartbeat and the terminal scheduler mutation ordered without making
    one slow receipt write starve unrelated jobs.
    """

    def __init__(self, scheduler: Scheduler, jobs: tuple[Job, ...]) -> None:
        self._scheduler = scheduler
        self._interval = max(0.01, min(10.0, scheduler.lease_seconds / 3.0))
        self._jobs = {job.id: job for job in jobs}
        self._locks = {job.id: Lock() for job in jobs}
        self._state_lock = Lock()
        self._stale: set[str] = set()
        self._stop = Event()
        self._thread = Thread(
            target=self._run,
            name="whole-os-lease-heartbeats",
            daemon=True,
        )

    def __enter__(self) -> _LeaseHeartbeats:
        # Refresh synchronously before worker submission, then let the dedicated
        # loop own cadence independently of coordinator scheduling and fsync.
        self._heartbeat_once()
        self._thread.start()
        return self

    def __exit__(self, kind: object, value: object, traceback: object) -> None:
        self._stop.set()
        self._thread.join(timeout=max(1.0, self._interval * 2.0))

    def _is_active(self, job_id: str) -> bool:
        with self._state_lock:
            return job_id in self._jobs

    def is_stale(self, job: Job) -> bool:
        with self._state_lock:
            return job.id in self._stale

    def _heartbeat_once(self) -> None:
        with self._state_lock:
            jobs = tuple(self._jobs.values())
        for job in jobs:
            lock = self._locks[job.id]
            if not lock.acquire(blocking=False):
                # A terminal mutation for this exact job is already in progress.
                continue
            try:
                if not self._is_active(job.id):
                    continue
                try:
                    self._scheduler.heartbeat(job.id, job.lease_token or "")
                except StaleLeaseError:
                    with self._state_lock:
                        self._stale.add(job.id)
                        self._jobs.pop(job.id, None)
            finally:
                lock.release()

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            self._heartbeat_once()

    def transition(self, job: Job, action: Callable[[], object]) -> None:
        """Run one final mutation ordered after the job's last heartbeat."""
        lock = self._locks[job.id]
        with lock:
            with self._state_lock:
                if job.id in self._stale or job.id not in self._jobs:
                    raise StaleLeaseError("scheduler lease expired before transition")
            try:
                # Do not rely on where the periodic loop happened to fall. The
                # terminal mutation always starts from a freshly persisted lease,
                # ordered under this job's transition lock.
                self._scheduler.heartbeat(job.id, job.lease_token or "")
            except StaleLeaseError:
                with self._state_lock:
                    self._stale.add(job.id)
                    self._jobs.pop(job.id, None)
                raise
            action()
            with self._state_lock:
                self._jobs.pop(job.id, None)


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


class WholeOSTerminalAssessor(Protocol):
    """Optional host capability required to complete a successful campaign."""

    def assess_terminal_candidate(
        self,
        candidate: ConvergenceResult,
        payload: Mapping[str, Any],
    ) -> TerminalAssessment:
        """Perform the one candidate-bound Curator assessment."""
        ...


class WholeOSReplayValidator(Protocol):
    """Optional host capability guarding replay of a retained package success.

    The service keeps its own durable package receipt, so a package that finished
    once would otherwise be reported successful forever, even after the host's
    admission was revoked or the evidence behind it was corrupted.  A host that
    holds such external evidence implements this method; the service then treats
    a retained success as current only while it returns ``None``.

    A host without the method keeps the original behaviour: the service trusts
    its own receipt.  No default verifier is supplied on purpose, because a
    default could only pretend to verify evidence it cannot see.
    """

    def validate_retained_package_result(
        self,
        package: OutcomeWorkPackage,
        result: PackageExecutionResult,
        payload: Mapping[str, Any],
    ) -> str | None:
        """Return ``None`` if still valid, otherwise a nonempty reason.

        Must be read-only: it runs on every observation and on every resume.
        """
        ...


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
    recent_results: tuple[PackageExecutionResult, ...] = ()
    terminal_assessment: TerminalAssessment | None = None
    terminal_message: str = ""


class WholeOSService:
    JOB_KIND = "whole-os-package"
    TERMINAL_JOB_KIND = "whole-os-terminal-assessment"

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
        self._kickoff = self._build_kickoff()
        campaign_key = canonical_digest(
            {
                "campaign_id": config.campaign_id,
                "tenant_id": config.tenant_id,
                "repository_id": config.repository_id,
            }
        ).removeprefix("sha256:")
        self._receipt_dir = config.state_dir / "whole-os-receipts" / campaign_key
        self._package_receipt_dir = self._receipt_dir / "packages"
        with self._invocation():
            self._enqueue_ready()

    def _build_kickoff(self) -> dict[str, object]:
        context: dict[str, object] = {
            "campaign_id": self.config.campaign_id,
            "tenant_id": self.config.tenant_id,
            "repository_id": self.config.repository_id,
            "configuration_digest": self.config.binding_descriptor.digest,
            "graph_digest": self.config.graph.digest,
            "base_snapshot": self.config.graph.base_snapshot,
        }
        return {
            "schema_version": 1,
            "context_digest": canonical_digest(context),
            "context": context,
        }

    def _jobs(self) -> tuple[Job, ...]:
        return tuple(
            job
            for job in self.scheduler.jobs()
            if job.kind == self.JOB_KIND and job.mission_id == self.config.campaign_id
        )

    def _terminal_jobs(self) -> tuple[Job, ...]:
        return tuple(
            job
            for job in self.scheduler.jobs()
            if job.kind == self.TERMINAL_JOB_KIND
            and job.mission_id == self.config.campaign_id
        )

    @contextmanager
    def _invocation(self) -> Iterator[None]:
        """Open the fresh validation scope of ONE public call.

        Every public entry (constructor, ``run_once``, ``run_cohort``,
        ``run_to_completion``, ``observe``) enters this and always installs a new
        scope, whatever the execution context already holds.  The presence of an
        inherited entry therefore proves nothing: a copied ``contextvars`` context, a
        propagated task context or a re-entrant public call from a host all
        revalidate with the host.  Private helpers (``_observe``, ``_run_cohort``,
        ``_classify_done`` ...) assume their public caller opened the scope and share
        its memo, which is what keeps one call from asking the host repeatedly.  On
        exit the scope is closed, so a context copied inside the call cannot reuse
        its verdicts even when it is kept alive afterwards.
        """
        scope = _RetainedScope()
        token = _RETAINED_SCOPES.set({**(_RETAINED_SCOPES.get() or {}), id(self): scope})
        try:
            yield
        finally:
            scope.open = False
            scope.verdicts.clear()
            _RETAINED_SCOPES.reset(token)

    def _check_retained(self, package_id: str) -> str | None:
        """Ask the host whether a retained success is still valid (fail closed)."""
        validator = getattr(self.host, "validate_retained_package_result", None)
        if not callable(validator):
            return None
        package = self.by_id.get(package_id)
        if package is None:
            return "package is absent from the sealed graph"
        try:
            result = self._load_package_result(package_id)
            reason = validator(
                package, result, self._freeze(self._payload(package))
            )
        except Exception as exc:
            return f"{type(exc).__name__}: {exc}"
        if reason is None:
            return None
        if type(reason) is not str or not reason.strip():
            return "host returned an untyped replay verdict"
        return reason

    def _retained_rejection(self, package_id: str) -> str | None:
        scope = (_RETAINED_SCOPES.get() or {}).get(id(self))
        memo = scope.verdicts if scope is not None and scope.open else None
        if memo is not None and package_id in memo:
            return memo[package_id]
        reason = self._check_retained(package_id)
        if memo is not None:
            memo[package_id] = reason
        return reason

    def _classify_done(self) -> tuple[set[str], dict[str, str]]:
        """Split scheduler-``done`` packages into currently valid and rejected."""
        valid: set[str] = set()
        rejected: dict[str, str] = {}
        done = {
            str(job.payload["package_id"])
            for job in self._jobs()
            if job.state == "done"
        }
        for package_id in sorted(done):
            reason = self._retained_rejection(package_id)
            if reason is None:
                valid.add(package_id)
            else:
                rejected[package_id] = reason
        return valid, rejected

    def _completed(self) -> set[str]:
        return self._classify_done()[0]

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
            "cohort_kickoff": self._kickoff,
        }

    @staticmethod
    def _canonical_bytes(document: Mapping[str, object]) -> bytes:
        return (
            json.dumps(
                dict(document),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")

    @staticmethod
    def _write_once(path: Path, document: Mapping[str, object]) -> None:
        """Durably create one canonical receipt, rejecting conflicting replay."""
        body = WholeOSService._canonical_bytes(document)
        target = filesystem_path(path)
        filesystem_path(path.parent).mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.read_bytes() != body:
                raise ServiceError(
                    f"durable receipt conflicts with replay: {path.name}"
                )
            return
        temporary = filesystem_path(
            path.with_name(f".{path.name}.{uuid4()}.tmp")
        )
        try:
            with temporary.open("xb") as handle:
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            # Job leases serialize writers. Replace makes a fully flushed receipt
            # visible before the corresponding scheduler transition is committed.
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    def _package_receipt_path(self, package_id: str) -> Path:
        key = canonical_digest({"package_id": package_id}).removeprefix("sha256:")
        return self._package_receipt_dir / f"{key}.json"

    def _package_result_document(
        self, result: PackageExecutionResult
    ) -> dict[str, object]:
        return {
            "schema_version": 1,
            "campaign_id": self.config.campaign_id,
            "graph_digest": self.config.graph.digest,
            "package_id": result.package_id,
            "status": result.status.value,
            "candidate_digest": result.candidate_digest,
            "evidence_refs": list(result.evidence_refs),
            "message": result.message,
        }

    def _persist_package_result(self, result: PackageExecutionResult) -> None:
        self._write_once(
            self._package_receipt_path(result.package_id),
            self._package_result_document(result),
        )

    def _load_package_result(self, package_id: str) -> PackageExecutionResult:
        path = filesystem_path(self._package_receipt_path(package_id))
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ServiceError(
                f"successful package {package_id} lacks a valid durable receipt"
            ) from exc
        if not isinstance(document, dict):
            raise ServiceError(f"package receipt {package_id} is not an object")
        required = {
            "schema_version",
            "campaign_id",
            "graph_digest",
            "package_id",
            "status",
            "candidate_digest",
            "evidence_refs",
            "message",
        }
        if (
            set(document) != required
            or document["schema_version"] != 1
            or document["campaign_id"] != self.config.campaign_id
            or document["graph_digest"] != self.config.graph.digest
            or document["package_id"] != package_id
            or not isinstance(document["evidence_refs"], list)
            or any(type(item) is not str for item in document["evidence_refs"])
            or type(document["message"]) is not str
        ):
            raise ServiceError(f"package receipt {package_id} is invalid")
        try:
            result = PackageExecutionResult(
                package_id,
                PackageStatus(document["status"]),
                document["candidate_digest"],
                tuple(document["evidence_refs"]),
                document["message"],
            )
        except (TypeError, ValueError) as exc:
            raise ServiceError(f"package receipt {package_id} is invalid") from exc
        if result.status not in {PackageStatus.COMPLETED, PackageStatus.NO_CHANGE}:
            raise ServiceError(f"package receipt {package_id} is not successful")
        return result

    def _retained_package_result(
        self, package_id: str
    ) -> PackageExecutionResult | None:
        """Inspect the durable effect receipt before any retryable host call.

        A retained success the host no longer vouches for is not returned: the
        package then goes back to the host, which owns the typed blocker.  This
        path never starts a worker itself.
        """
        if not filesystem_path(self._package_receipt_path(package_id)).exists():
            return None
        if self._check_retained(package_id) is not None:
            return None
        return self._load_package_result(package_id)

    def _terminal_candidate(self) -> ConvergenceResult:
        if len(self._completed()) != len(self.by_id):
            raise ServiceError("terminal candidate requires all packages to complete")
        results = tuple(
            self._load_package_result(package.package_id)
            for package in self.config.graph.packages
        )
        output = {
            "schema_version": 1,
            "campaign_id": self.config.campaign_id,
            "tenant_id": self.config.tenant_id,
            "repository_id": self.config.repository_id,
            "graph_digest": self.config.graph.digest,
            "kickoff_digest": self._kickoff["context_digest"],
            "packages": [
                {
                    "package_id": result.package_id,
                    "candidate_digest": result.candidate_digest,
                    "evidence_refs": list(result.evidence_refs),
                }
                for result in results
            ],
        }
        return ConvergenceResult(True, output, "whole-OS package candidate converged")

    def _terminal_payload(self, candidate: ConvergenceResult) -> dict[str, object]:
        return {
            "schema_version": 1,
            "campaign_id": self.config.campaign_id,
            "tenant_id": self.config.tenant_id,
            "repository_id": self.config.repository_id,
            "graph_digest": self.config.graph.digest,
            "candidate_digest": convergence_candidate_digest(candidate),
        }

    def _terminal_receipt_path(self, candidate_digest: str) -> Path:
        return (
            self._receipt_dir
            / f"terminal-{candidate_digest.removeprefix('sha256:')}.json"
        )

    @staticmethod
    def _verification_document(verification: VerificationResult) -> dict[str, object]:
        return {
            "passed": verification.passed,
            "checks": list(verification.checks),
            "message": verification.message,
        }

    def _persist_terminal_assessment(
        self, candidate: ConvergenceResult, assessment: TerminalAssessment
    ) -> None:
        digest = convergence_candidate_digest(candidate)
        document = {
            **self._terminal_payload(candidate),
            "kind": "whole-os-terminal-assessment-v1",
            "verification": self._verification_document(assessment.verification),
            "evidence": assessment.evidence.to_document(),
        }
        self._write_once(self._terminal_receipt_path(digest), document)

    def _load_terminal_assessment(
        self, candidate: ConvergenceResult
    ) -> TerminalAssessment | None:
        digest = convergence_candidate_digest(candidate)
        path = filesystem_path(self._terminal_receipt_path(digest))
        if not path.exists():
            return None
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ServiceError("terminal assessment receipt is unreadable") from exc
        expected = {
            *self._terminal_payload(candidate),
            "kind",
            "verification",
            "evidence",
        }
        if (
            not isinstance(document, dict)
            or set(document) != expected
            or document.get("kind") != "whole-os-terminal-assessment-v1"
            or any(
                document.get(key) != value
                for key, value in self._terminal_payload(candidate).items()
            )
        ):
            raise ServiceError("terminal assessment receipt is not candidate-bound")
        verification = document.get("verification")
        evidence = document.get("evidence")
        if not isinstance(verification, dict) or not isinstance(evidence, dict):
            raise ServiceError("terminal assessment receipt is untyped")
        if set(verification) != {"passed", "checks", "message"} or not isinstance(
            verification["checks"], list
        ):
            raise ServiceError("terminal verification receipt is invalid")
        try:
            restored = TerminalAssessment(
                VerificationResult(
                    verification["passed"],
                    tuple(verification["checks"]),
                    verification["message"],
                ),
                TerminalEvidence.from_document(evidence),
            )
        except (TypeError, ValueError) as exc:
            raise ServiceError("terminal assessment receipt is invalid") from exc
        if restored.evidence.candidate_digest != digest:
            raise ServiceError("terminal evidence targets another candidate")
        return restored

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

    def _enqueue_terminal_ready(self) -> None:
        if len(self._completed()) != len(self.by_id):
            return
        candidate = self._terminal_candidate()
        payload = self._terminal_payload(candidate)
        if not any(job.payload == payload for job in self._terminal_jobs()):
            self.scheduler.enqueue(
                self.TERMINAL_JOB_KIND,
                payload,
                max_attempts=self.config.maximum_attempts,
                mission_id=self.config.campaign_id,
            )

    def _run_terminal_assessment_if_ready(self) -> None:
        """Claim, assess, and durably seal the completed package candidate once."""
        self._enqueue_terminal_ready()
        if len(self._completed()) != len(self.by_id):
            # A package whose retained success was rejected is not complete, so
            # no terminal candidate exists to load or assess.
            return
        jobs = self._terminal_jobs()
        if not jobs:
            return
        candidate = self._terminal_candidate()
        payload = self._terminal_payload(candidate)
        matching = next((job for job in jobs if job.payload == payload), None)
        if matching is None or matching.state in {"done", "dead-letter"}:
            return
        owner = f"whole-os:{self.config.campaign_id}:terminal:{uuid4()}"
        job = self.scheduler.claim(
            owner,
            kind=self.TERMINAL_JOB_KIND,
            mission_id=self.config.campaign_id,
            job_id=matching.id,
            resource_ids=(
                canonical_digest(
                    {
                        "tenant_id": self.config.tenant_id,
                        "repository_id": self.config.repository_id,
                        "campaign_id": self.config.campaign_id,
                        "kind": "terminal-assessment",
                    }
                ),
            ),
        )
        if job is None:
            return
        token = job.lease_token or ""
        with _LeaseHeartbeats(self.scheduler, (job,)) as heartbeats:
            try:
                retained = self._load_terminal_assessment(candidate)
                if retained is None:
                    assessor = getattr(self.host, "assess_terminal_candidate", None)
                    if not callable(assessor):
                        raise ServiceError("host terminal assessor is required")
                    frozen_payload = self._freeze(payload)
                    assert isinstance(frozen_payload, Mapping)
                    assessment = assessor(candidate, frozen_payload)
                    if not isinstance(assessment, TerminalAssessment):
                        raise ServiceError(
                            "host returned an untyped terminal assessment"
                        )
                    if assessment.evidence.candidate_digest != (
                        convergence_candidate_digest(candidate)
                    ):
                        raise ServiceError(
                            "terminal evidence does not bind the converged candidate"
                        )
                    self._persist_terminal_assessment(candidate, assessment)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                try:
                    heartbeats.transition(
                        job,
                        lambda error=error: self.scheduler.fail(
                            job.id,
                            token,
                            error,
                            mission_id=self.config.campaign_id,
                        ),
                    )
                except StaleLeaseError:
                    # No effect is retried here. A later cohort can reclaim the
                    # expired exact job and reconcile any retained receipt.
                    return
                return
            try:
                heartbeats.transition(
                    job,
                    lambda: self.scheduler.complete(
                        job.id, token, mission_id=self.config.campaign_id
                    ),
                )
            except StaleLeaseError:
                return

    def run_once(self) -> ServiceObservation:
        """Execute one package using the original strict compatibility behavior."""
        with self._invocation():
            return self._run_once()

    def _run_once(self) -> ServiceObservation:
        jobs = self._claim_cohort(
            f"whole-os:{self.config.campaign_id}:strict", maximum=1
        )
        if not jobs:
            self._run_terminal_assessment_if_ready()
            return self._observe(None, ())
        job = jobs[0]
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
            retained = self._retained_package_result(package_id)
            if retained is not None:
                self._persist_result(job, retained)
                self._enqueue_ready()
                self._run_terminal_assessment_if_ready()
                return self._observe(retained, ())
            resolved = self.bindings.resolve(job.payload, self.config.state_dir)
            result = self.host.execute_package(package, resolved, job.payload)
            if result.package_id != package_id:
                raise ServiceError("host returned a cross-package result")
            if result.status in {PackageStatus.COMPLETED, PackageStatus.NO_CHANGE}:
                self._persist_result(job, result)
                self._enqueue_ready()
            else:
                self.scheduler.fail(
                    job.id,
                    job.lease_token or "",
                    result.status.value + ": " + result.message,
                    mission_id=self.config.campaign_id,
                )
            self._run_terminal_assessment_if_ready()
            return self._observe(result, ())
        except Exception as exc:
            self.scheduler.fail(
                job.id,
                job.lease_token or "",
                f"{type(exc).__name__}: {exc}",
                mission_id=self.config.campaign_id,
            )
            return self._observe(
                PackageExecutionResult(
                    package_id, PackageStatus.FAILED, None, (), str(exc)
                ),
                (),
            )

    @staticmethod
    def _freeze(value: Any) -> Any:
        if isinstance(value, dict):
            return MappingProxyType(
                {key: WholeOSService._freeze(item) for key, item in value.items()}
            )
        if isinstance(value, list):
            return tuple(WholeOSService._freeze(item) for item in value)
        return value

    def _resource_ids(self, package: OutcomeWorkPackage) -> tuple[str, ...]:
        """Return subject-bound identities for durable scheduler arbitration."""
        subject = {
            "tenant_id": self.config.tenant_id,
            "repository_id": self.config.repository_id,
        }
        resources = (
            *(
                canonical_digest({**subject, "kind": "write-path", "value": path})
                for path in package.allowed_paths
            ),
            *(
                canonical_digest({**subject, "kind": "semantic-lock", "value": lock})
                for lock in package.semantic_locks
            ),
        )
        return tuple(sorted(set(resources)))

    def _claim_cohort(
        self, owner: str, *, maximum: int | None = None
    ) -> tuple[Job, ...]:
        claimed: list[Job] = []
        paths: set[str] = set()
        locks: set[str] = set()
        capacity = maximum or self.config.graph.maximum_concurrent
        completed = self._completed()
        for candidate in self._jobs():
            if len(claimed) >= capacity:
                break
            if candidate.state not in {"ready", "leased"}:
                continue
            package = self.by_id.get(str(candidate.payload.get("package_id", "")))
            if package is not None and not set(package.dependencies) <= completed:
                # Already queued, but a dependency is no longer currently valid.
                continue
            if package is not None and (
                paths.intersection(package.allowed_paths)
                or locks.intersection(package.semantic_locks)
            ):
                continue
            job = self.scheduler.claim(
                owner,
                kind=self.JOB_KIND,
                mission_id=self.config.campaign_id,
                job_id=candidate.id,
                resource_ids=() if package is None else self._resource_ids(package),
            )
            if job is None:
                continue
            claimed.append(job)
            if package is not None:
                paths.update(package.allowed_paths)
                locks.update(package.semantic_locks)
        return tuple(claimed)

    def _execute_claimed(self, job: Job) -> PackageExecutionResult:
        package_id = str(job.payload.get("package_id", ""))
        package = self.by_id.get(package_id)
        if package is None:
            return PackageExecutionResult(
                package_id or "unknown",
                PackageStatus.FAILED,
                None,
                (),
                "queued package is absent from the sealed graph",
            )
        try:
            payload = dict(job.payload)
            # Jobs created before cohort support remain resumable. The kickoff is
            # deterministic for the sealed campaign and is supplied at execution.
            payload.setdefault("cohort_kickoff", self._kickoff)
            if payload != self._payload(package):
                raise ServiceError("queued package payload differs from sealed graph")
            retained = self._retained_package_result(package_id)
            if retained is not None:
                return retained
            frozen_payload = self._freeze(payload)
            assert isinstance(frozen_payload, Mapping)
            resolved = self.bindings.resolve(frozen_payload, self.config.state_dir)
            result = self.host.execute_package(package, resolved, frozen_payload)
            if not isinstance(result, PackageExecutionResult):
                raise ServiceError("host returned an untyped package result")
            if result.package_id != package_id:
                raise ServiceError("host returned a cross-package result")
            return result
        except Exception as exc:
            return PackageExecutionResult(
                package_id, PackageStatus.FAILED, None, (), str(exc)
            )

    def _persist_result(self, job: Job, result: PackageExecutionResult) -> None:
        token = job.lease_token or ""
        if result.status in {PackageStatus.COMPLETED, PackageStatus.NO_CHANGE}:
            self._persist_package_result(result)
            self.scheduler.complete(job.id, token, mission_id=self.config.campaign_id)
        elif result.status in {
            PackageStatus.BLOCKED_AUTHORITY,
            PackageStatus.BLOCKED_CAPABILITY,
        }:
            self.scheduler.dead_letter(
                job.id,
                token,
                result.status.value + ": " + result.message,
                mission_id=self.config.campaign_id,
            )
        else:
            self.scheduler.fail(
                job.id,
                token,
                result.status.value + ": " + result.message,
                mission_id=self.config.campaign_id,
            )

    def _persist_result_with_heartbeats(
        self,
        job: Job,
        result: PackageExecutionResult,
        heartbeats: _LeaseHeartbeats,
    ) -> None:
        """Persist a result without suspending lease renewal across receipt fsync."""
        token = job.lease_token or ""
        if result.status in {PackageStatus.COMPLETED, PackageStatus.NO_CHANGE}:
            # The receipt is the recoverable side of the receipt/queue boundary.
            # Keep heartbeating while it is flushed, then serialize only the final
            # scheduler transition against the lease-keeper thread.
            self._persist_package_result(result)
            heartbeats.transition(
                job,
                lambda: self.scheduler.complete(
                    job.id, token, mission_id=self.config.campaign_id
                ),
            )
        elif result.status in {
            PackageStatus.BLOCKED_AUTHORITY,
            PackageStatus.BLOCKED_CAPABILITY,
        }:
            heartbeats.transition(
                job,
                lambda: self.scheduler.dead_letter(
                    job.id,
                    token,
                    result.status.value + ": " + result.message,
                    mission_id=self.config.campaign_id,
                ),
            )
        else:
            heartbeats.transition(
                job,
                lambda: self.scheduler.fail(
                    job.id,
                    token,
                    result.status.value + ": " + result.message,
                    mission_id=self.config.campaign_id,
                ),
            )

    def run_cohort(self) -> ServiceObservation:
        """Run one durable, capacity-bounded dependency-ready package wave.

        Every host receives the same digest-bound immutable kickoff in its payload.
        Scheduler leases are heartbeated while host work is active, and all queue
        transitions occur on the coordinating thread after execution completes.
        """
        with self._invocation():
            return self._run_cohort()

    def _run_cohort(self) -> ServiceObservation:
        self._enqueue_ready()
        owner = f"whole-os:{self.config.campaign_id}:cohort:{uuid4()}"
        jobs = self._claim_cohort(owner)
        if not jobs:
            self._run_terminal_assessment_if_ready()
            return self._observe(None, ())

        results: dict[str, PackageExecutionResult] = {}
        with _LeaseHeartbeats(self.scheduler, jobs) as heartbeats:
            with ThreadPoolExecutor(
                max_workers=len(jobs),
                thread_name_prefix=f"whole-os-{self.config.campaign_id}",
            ) as pool:
                active: dict[Future[PackageExecutionResult], Job] = {
                    pool.submit(self._execute_claimed, job): job
                    for job in jobs
                    if not heartbeats.is_stale(job)
                }
                while active:
                    completed, _ = wait(
                        tuple(active),
                        return_when=FIRST_COMPLETED,
                    )
                    for future in completed:
                        job = active.pop(future)
                        result = future.result()
                        try:
                            self._persist_result_with_heartbeats(
                                job, result, heartbeats
                            )
                        except StaleLeaseError:
                            result = PackageExecutionResult(
                                result.package_id,
                                PackageStatus.FAILED,
                                None,
                                result.evidence_refs,
                                "scheduler lease expired before result persistence",
                            )
                        results[result.package_id] = result

        self._enqueue_ready()
        self._run_terminal_assessment_if_ready()
        ordered = tuple(
            results[package.package_id]
            for package in self.config.graph.packages
            if package.package_id in results
        )
        return self._observe(ordered[-1] if ordered else None, ordered)

    def run_to_completion(
        self, *, maximum_cohorts: int | None = None
    ) -> ServiceObservation:
        """Run bounded cohort waves until terminal or no immediate progress exists.

        The default bound covers every configured package attempt once. Backoff,
        active foreign leases, and an explicit lower bound return durable status to
        the caller instead of spinning or sleeping indefinitely.
        """
        if maximum_cohorts is not None and (
            type(maximum_cohorts) is not int or maximum_cohorts < 1
        ):
            raise ServiceError("maximum_cohorts must be a positive integer")
        limit = maximum_cohorts or max(
            1, (len(self.by_id) + 1) * self.config.maximum_attempts
        )
        all_results: list[PackageExecutionResult] = []
        observation = self.observe()
        for _ in range(limit):
            before = tuple(
                (job.id, job.state, job.attempts, job.last_error)
                for job in (*self._jobs(), *self._terminal_jobs())
            )
            observation = self.run_cohort()
            all_results.extend(observation.recent_results)
            if observation.status in {"complete", "blocked"}:
                break
            after = tuple(
                (job.id, job.state, job.attempts, job.last_error)
                for job in (*self._jobs(), *self._terminal_jobs())
            )
            if before == after:
                break
        return self.observe(
            last_result=all_results[-1] if all_results else observation.last_result,
            recent_results=tuple(all_results),
        )

    def observe(
        self,
        *,
        last_result: PackageExecutionResult | None = None,
        recent_results: tuple[PackageExecutionResult, ...] = (),
    ) -> ServiceObservation:
        with self._invocation():
            return self._observe(last_result, recent_results)

    def _observe(
        self,
        last_result: PackageExecutionResult | None,
        recent_results: tuple[PackageExecutionResult, ...],
    ) -> ServiceObservation:
        jobs = self._jobs()
        # A retained success the host no longer vouches for is history, not
        # completion: it is reported as blocked, never as complete.  The retained
        # receipts themselves stay untouched for audit.
        valid, rejected = self._classify_done()
        completed = tuple(sorted(valid))
        blocked_set = {
            str(job.payload["package_id"]) for job in jobs if job.state == "dead-letter"
        } | set(rejected)
        changed = True
        while changed:
            changed = False
            for package in self.config.graph.packages:
                if package.package_id not in blocked_set and blocked_set.intersection(
                    package.dependencies
                ):
                    blocked_set.add(package.package_id)
                    changed = True
        blocked = tuple(sorted(blocked_set))
        enqueued = {str(job.payload["package_id"]) for job in jobs}
        pending = tuple(sorted(set(self.by_id) - set(completed)))
        terminal_assessment: TerminalAssessment | None = None
        terminal_message = ""
        if len(completed) == len(self.by_id):
            try:
                candidate = self._terminal_candidate()
                terminal_assessment = self._load_terminal_assessment(candidate)
                terminal_jobs = self._terminal_jobs()
                if terminal_assessment is not None:
                    if terminal_assessment.verification.passed:
                        status = "complete"
                    else:
                        status = "blocked"
                        terminal_message = terminal_assessment.verification.message
                elif any(job.state == "dead-letter" for job in terminal_jobs):
                    status = "blocked"
                    terminal_message = next(
                        (
                            job.last_error or "terminal assessment failed"
                            for job in terminal_jobs
                            if job.state == "dead-letter"
                        ),
                        "terminal assessment failed",
                    )
                else:
                    status = "terminal_assessment_pending"
                    terminal_message = "candidate-bound terminal assessment is pending"
            except ServiceError as exc:
                status = "blocked"
                terminal_message = str(exc)
        elif any(
            job.state in {"ready", "leased"}
            and str(job.payload["package_id"]) not in blocked_set
            for job in jobs
        ):
            status = "ready"
        elif blocked:
            status = "blocked"
        elif set(self.by_id) - enqueued:
            status = "dependency_wait"
        else:
            status = "idle"
        if rejected:
            terminal_message = "retained success failed revalidation: " + "; ".join(
                f"{package_id}: {reason}" for package_id, reason in sorted(rejected.items())
            )
        return ServiceObservation(
            self.config.campaign_id,
            status,
            completed,
            pending,
            blocked,
            last_result,
            recent_results,
            terminal_assessment,
            terminal_message,
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
    if type(contract_version) is not int or type(maximum_concurrent) is not int:
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
    "WholeOSTerminalAssessor",
    "graph_from_document",
    "load_graph",
    "load_service_config",
]
