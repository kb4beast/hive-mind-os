"""Replaceable, fail-closed N28 package composition for :mod:`whole_os_service`.

``WholeOSService`` owns durable graph scheduling.  This module supplies a host
implementation which makes the work inside one package explicit: repository
profile admission, evidence-backed discovery, bounded building, independent
qualification, delivery, PR feedback, and scoped learning.  Privileged
executors and credentials remain injected host adapters.

Roblox runtime and tournament inputs are qualification evidence, not ambient
capabilities.  Their absence is reported by ``readiness`` and blocks only a
package whose policy explicitly requires that evidence.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, Protocol
from uuid import uuid4

from .benchmark_adapters import PinnedRecipeAdapter
from .brain_kernel.canonical import canonical_digest, canonical_document
from .builder_session import (
    BuilderDisposition,
    BuilderSession,
    BuilderSessionResult,
    BuilderSessionSpec,
)
from .candidate_qualification import (
    CandidateQualifier,
    QualificationDisposition,
    QualificationReceipt,
    QualificationRequest,
)
from .cohort_assurance import TerminalAssessment
from .cohort_runtime import ConvergenceResult
from .delivery_broker import (
    ArtifactKind,
    DeliveryBroker,
    DeliveryRequest,
    DeliveryResult,
    DeliveryState,
)
from .discovery_backlog import BacklogSelection, DiscoveryBacklog
from .outcome_graph import OutcomeWorkPackage
from .pr_feedback import FeedbackDecision, FeedbackObservation, FeedbackObserver
from .receipts import filesystem_path
from .repository_profile import ProfileCapability, RepositoryProfile
from .roblox_profile import RobloxProfile
from .roblox_runtime import RobloxRuntimeEvidence, RuntimeVerdict
from .scoped_learning import LearningRoute, LearningScope
from .whole_os_qualification import CompositionManifest
from .whole_os_service import (
    PackageExecutionResult,
    PackageStatus,
    ServiceError,
)


class CompositionError(ServiceError):
    """A configured composition boundary is malformed or contradicted."""


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _base_snapshot(payload: Mapping[str, Any]) -> str:
    kickoff = payload.get("cohort_kickoff")
    if not isinstance(kickoff, Mapping):
        raise CompositionError("cohort kickoff is absent")
    context = kickoff.get("context")
    if not isinstance(context, Mapping):
        raise CompositionError("cohort kickoff context is absent")
    snapshot = context.get("base_snapshot")
    if type(snapshot) is not str or not snapshot:
        raise CompositionError("base snapshot is absent from cohort kickoff")
    return snapshot


class BlockerKind(StrEnum):
    BLOCKED_AUTHORITY = "BLOCKED_AUTHORITY"
    BLOCKED_CAPABILITY = "BLOCKED_CAPABILITY"
    BLOCKED_SOURCE = "BLOCKED_SOURCE"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


@dataclass(frozen=True, slots=True)
class CompositionBlocker:
    stage: str
    kind: BlockerKind
    detail: str

    def __post_init__(self) -> None:
        if not self.stage.strip() or not self.detail.strip():
            raise CompositionError("composition blocker must name its stage and detail")

    @property
    def reference(self) -> str:
        return canonical_digest(canonical_document(self))

    @property
    def message(self) -> str:
        return f"{self.kind.value}:{self.stage}:{self.detail}"


@dataclass(frozen=True, slots=True)
class DiscoveryOutcome:
    selection: BacklogSelection
    evidence_refs: tuple[str, ...]
    court_receipt: str

    def __post_init__(self) -> None:
        selected = self.selection.selected_ids
        candidate_ids = {item.idea_id for item in self.selection.candidates}
        if len(selected) != 1 or selected[0] not in candidate_ids:
            raise CompositionError("discovery must select one admitted candidate")
        if not self.evidence_refs or not self.court_receipt.strip():
            raise CompositionError("discovery requires evidence and a court receipt")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise CompositionError("discovery evidence references must be unique")

    @property
    def digest(self) -> str:
        return canonical_digest(canonical_document(self))


@dataclass(frozen=True, slots=True)
class BuildOutcome:
    result: BuilderSessionResult
    candidate_commit: str
    candidate_tree: str
    target_runtime_imports_hive: bool

    def __post_init__(self) -> None:
        if self.result.candidate != self.candidate_commit:
            raise CompositionError("builder result and candidate commit differ")
        if not self.candidate_commit.strip() or not self.candidate_tree.startswith(
            "sha256:"
        ):
            raise CompositionError(
                "builder must return exact commit and tree identities"
            )
        if self.target_runtime_imports_hive is not False:
            raise CompositionError("delivered target must not import Hive at runtime")


class DiscoveryAdapter(Protocol):
    def discover(
        self, package: OutcomeWorkPackage, payload: Mapping[str, Any]
    ) -> DiscoveryOutcome: ...


class BuilderAdapter(Protocol):
    def build(
        self,
        package: OutcomeWorkPackage,
        discovery: DiscoveryOutcome,
        payload: Mapping[str, Any],
    ) -> BuildOutcome: ...


class FeedbackSource(Protocol):
    def observations(
        self, delivery: DeliveryResult, package: OutcomeWorkPackage
    ) -> tuple[FeedbackObservation, ...]: ...


class LearningRecorder(Protocol):
    def record(self, route: LearningRoute) -> str: ...


class TerminalCurator(Protocol):
    curator_id: str

    def assess(
        self, candidate: ConvergenceResult, payload: Mapping[str, Any]
    ) -> TerminalAssessment: ...


@dataclass(frozen=True, slots=True)
class DeliveryPolicy:
    target: str
    base: str
    run_branch_prefix: str
    grant_ref: str
    qualification_sandbox_digest: str
    qualification_toolchain_digest: str
    qualification_environment_digest: str
    evaluator_id: str
    learning_scope: LearningScope = LearningScope.TARGET_APP
    learning_destination_subject_id: str | None = None
    learning_authorization_digest: str = ""
    learning_export_destination: str | None = None
    publish_required: bool = True
    feedback_required: bool = True
    roblox_runtime_required: bool = False

    def __post_init__(self) -> None:
        required = (
            self.target,
            self.base,
            self.run_branch_prefix,
            self.grant_ref,
            self.qualification_sandbox_digest,
            self.qualification_toolchain_digest,
            self.qualification_environment_digest,
            self.evaluator_id,
            self.learning_authorization_digest,
        )
        if any(type(value) is not str or not value.strip() for value in required):
            raise CompositionError("delivery and qualification policy must be sealed")
        if self.run_branch_prefix in {self.base, "main", "master"}:
            raise CompositionError("composition branch prefix cannot be protected")
        if self.learning_scope is LearningScope.EXPORT_DRAFT and not (
            self.learning_destination_subject_id and self.learning_export_destination
        ):
            raise CompositionError("export learning requires a subject and destination")


@dataclass(frozen=True, slots=True)
class CompositionReadiness:
    profile_id: str
    check_class: str
    runtime_supported: bool
    compile_supported: bool
    roblox_runtime: str
    tournament_recipe_digests: tuple[str, ...]
    blockers: tuple[CompositionBlocker, ...]


class BacklogDiscoveryAdapter:
    """Bind the existing deterministic backlog to the composition protocol."""

    def __init__(
        self,
        backlog: DiscoveryBacklog,
        *,
        evidence_refs: tuple[str, ...],
        court_receipt: str,
    ) -> None:
        self.backlog = backlog
        self.evidence_refs = evidence_refs
        self.court_receipt = court_receipt

    def discover(
        self, package: OutcomeWorkPackage, payload: Mapping[str, Any]
    ) -> DiscoveryOutcome:
        del package
        tenant = payload.get("tenant_id")
        repository = payload.get("repository_id")
        signals = tuple(self.backlog.signals.values())
        if not signals or any(
            signal.tenant_id != tenant or signal.repository_id != repository
            for signal in signals
        ):
            raise CompositionError(
                "discovery evidence targets another subject or is absent"
            )
        return DiscoveryOutcome(
            self.backlog.select(limit=1), self.evidence_refs, self.court_receipt
        )


BuildAction = Callable[[BuilderSession], BuilderSessionResult]


class BoundedBuilderAdapter:
    """Run an injected builder action inside the existing bounded session."""

    def __init__(
        self,
        action: BuildAction,
        *,
        candidate_tree: Callable[[BuilderSessionResult], str],
        target_runtime_imports_hive: bool = False,
    ) -> None:
        self.action = action
        self.candidate_tree = candidate_tree
        self.target_runtime_imports_hive = target_runtime_imports_hive

    def build(
        self,
        package: OutcomeWorkPackage,
        discovery: DiscoveryOutcome,
        payload: Mapping[str, Any],
    ) -> BuildOutcome:
        attempt = canonical_digest(
            {
                "package_id": package.package_id,
                "context_digest": payload.get("cohort_kickoff", {}).get(
                    "context_digest"
                )
                if isinstance(payload.get("cohort_kickoff"), Mapping)
                else None,
                "discovery_digest": discovery.digest,
            }
        )
        session = BuilderSession(
            BuilderSessionSpec(
                package.package_id,
                attempt,
                str(payload["tenant_id"]),
                _base_snapshot(payload),
                package.allowed_paths,
                acceptance_refs=package.acceptance_ids,
            )
        )
        result = session.run(self.action)
        if result.candidate is None:
            raise CompositionError("builder returned no candidate")
        return BuildOutcome(
            result,
            result.candidate,
            self.candidate_tree(result),
            self.target_runtime_imports_hive,
        )


class DurableLearningRecorder:
    """Append content-addressed scoped routes without activating a challenger."""

    def __init__(self, state_directory: str | Path) -> None:
        self.root = Path(state_directory).resolve()

    def record(self, route: LearningRoute) -> str:
        digest = route.digest
        path = self.root / f"{digest.removeprefix('sha256:')}.json"
        body = (
            json.dumps(
                route.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False
            )
            + "\n"
        ).encode("utf-8")
        target = filesystem_path(path)
        filesystem_path(path.parent).mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.read_bytes() != body:
                raise CompositionError("learning route conflicts with retained receipt")
            return digest
        temporary = filesystem_path(path.with_name(f".{path.name}.{uuid4()}.tmp"))
        try:
            with temporary.open("xb") as handle:
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return digest


class WholeOSCompositionHost:
    """A concrete ``WholeOSHost`` made from replaceable, typed stage adapters."""

    def __init__(
        self,
        *,
        state_directory: str | Path,
        manifest: CompositionManifest,
        profile_id: str,
        repository_profile: RepositoryProfile,
        discovery: DiscoveryAdapter,
        builder: BuilderAdapter,
        qualifier: CandidateQualifier,
        delivery: DeliveryBroker,
        delivery_policy: DeliveryPolicy,
        feedback_source: FeedbackSource | None,
        learning: LearningRecorder,
        curator: TerminalCurator,
        producer_id: str,
        roblox_profile: RobloxProfile | None = None,
        roblox_runtime: RobloxRuntimeEvidence | None = None,
        tournament_adapters: tuple[PinnedRecipeAdapter, ...] = (),
    ) -> None:
        selected = tuple(
            item for item in manifest.profiles if item.profile_id == profile_id
        )
        if len(selected) != 1:
            raise CompositionError(
                "selected profile is absent from composition manifest"
            )
        if repository_profile.identity.repository_id == producer_id:
            raise CompositionError(
                "producer identity must not reuse repository identity"
            )
        if curator.curator_id == producer_id:
            raise CompositionError("terminal curator must be independent from builder")
        recipe_digests = tuple(
            adapter.manifest.digest for adapter in tournament_adapters
        )
        if len(set(recipe_digests)) != len(recipe_digests):
            raise CompositionError("tournament recipe adapters must be unique")
        self.state_directory = Path(state_directory).resolve()
        self.manifest = manifest
        self.profile = selected[0]
        self.repository_profile = repository_profile
        self.discovery = discovery
        self.builder = builder
        self.qualifier = qualifier
        self.delivery = delivery
        self.delivery_policy = delivery_policy
        self.feedback_source = feedback_source
        self.learning = learning
        self.curator = curator
        self.producer_id = producer_id
        self.roblox_profile = roblox_profile
        self.roblox_runtime = roblox_runtime
        self.tournament_adapters = tournament_adapters
        self.feedback = FeedbackObserver()

    def readiness(self) -> CompositionReadiness:
        blockers: list[CompositionBlocker] = []
        runtime_state = "not-applicable"
        if self.profile.profile_id == "roblox":
            runtime_state = (
                self.roblox_runtime.verdict.value
                if self.roblox_runtime is not None
                else "unavailable"
            )
            if self.roblox_profile is None:
                blockers.append(
                    CompositionBlocker(
                        "roblox-profile",
                        BlockerKind.BLOCKED_SOURCE,
                        "admitted Roblox project profile is unavailable",
                    )
                )
            if self.roblox_runtime is None or self.roblox_runtime.verdict not in {
                RuntimeVerdict.RUNTIME_VALIDATED,
                RuntimeVerdict.PRODUCTION_CANDIDATE,
            }:
                blockers.append(
                    CompositionBlocker(
                        "roblox-runtime",
                        BlockerKind.BLOCKED_CAPABILITY,
                        "qualified Studio/runtime evidence is unavailable",
                    )
                )
        if not self.tournament_adapters:
            blockers.append(
                CompositionBlocker(
                    "tournament",
                    BlockerKind.BLOCKED_SOURCE,
                    "no pinned measured-tournament recipe adapter is admitted",
                )
            )
        return CompositionReadiness(
            self.profile.profile_id,
            self.profile.check_class,
            self.profile.runtime_supported,
            self.profile.compile_supported,
            runtime_state,
            tuple(adapter.manifest.digest for adapter in self.tournament_adapters),
            tuple(blockers),
        )

    def _receipt_path(self, payload: Mapping[str, Any], package_id: str) -> Path:
        key = canonical_digest(
            {
                "campaign_id": payload.get("campaign_id"),
                "tenant_id": payload.get("tenant_id"),
                "repository_id": payload.get("repository_id"),
                "graph_digest": payload.get("graph_digest"),
                "package_id": package_id,
            }
        ).removeprefix("sha256:")
        return self.state_directory / "composition-receipts" / f"{key}.json"

    @staticmethod
    def _write_once(path: Path, document: Mapping[str, Any]) -> None:
        body = (
            json.dumps(
                dict(document), sort_keys=True, separators=(",", ":"), allow_nan=False
            )
            + "\n"
        ).encode("utf-8")
        target = filesystem_path(path)
        filesystem_path(path.parent).mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.read_bytes() != body:
                raise CompositionError("composition receipt conflicts with replay")
            return
        temporary = filesystem_path(
            path.with_name(f".{path.name}.{uuid4()}.tmp")
        )
        try:
            with temporary.open("xb") as handle:
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _result_document(
        payload_digest: str, result: PackageExecutionResult
    ) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "kind": "whole-os-composition-result",
            "payload_digest": payload_digest,
            "package_id": result.package_id,
            "status": result.status.value,
            "candidate_digest": result.candidate_digest,
            "evidence_refs": list(result.evidence_refs),
            "message": result.message,
        }

    @staticmethod
    def _load_result(path: Path, payload_digest: str) -> PackageExecutionResult | None:
        target = filesystem_path(path)
        if not target.exists():
            return None
        try:
            document = json.loads(target.read_text(encoding="utf-8"))
            if (
                set(document)
                != {
                    "schema_version",
                    "kind",
                    "payload_digest",
                    "package_id",
                    "status",
                    "candidate_digest",
                    "evidence_refs",
                    "message",
                }
                or document["schema_version"] != 1
                or document["kind"] != "whole-os-composition-result"
                or document["payload_digest"] != payload_digest
                or not isinstance(document["evidence_refs"], list)
            ):
                raise CompositionError("composition replay receipt is invalid")
            return PackageExecutionResult(
                document["package_id"],
                PackageStatus(document["status"]),
                document["candidate_digest"],
                tuple(document["evidence_refs"]),
                document["message"],
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            if isinstance(exc, CompositionError):
                raise
            raise CompositionError("composition replay receipt is invalid") from exc

    def _finish(
        self,
        path: Path,
        payload_digest: str,
        result: PackageExecutionResult,
    ) -> PackageExecutionResult:
        self._write_once(path, self._result_document(payload_digest, result))
        return result

    def _blocked(
        self,
        package: OutcomeWorkPackage,
        path: Path,
        payload_digest: str,
        blocker: CompositionBlocker,
    ) -> PackageExecutionResult:
        status = (
            PackageStatus.BLOCKED_AUTHORITY
            if blocker.kind is BlockerKind.BLOCKED_AUTHORITY
            else PackageStatus.BLOCKED_CAPABILITY
        )
        return self._finish(
            path,
            payload_digest,
            PackageExecutionResult(
                package.package_id,
                status,
                None,
                (blocker.reference,),
                blocker.message,
            ),
        )

    def _validate_subject(
        self, payload: Mapping[str, Any]
    ) -> CompositionBlocker | None:
        identity = self.repository_profile.identity
        if (
            payload.get("tenant_id") != identity.tenant_id
            or payload.get("repository_id") != identity.repository_id
        ):
            return CompositionBlocker(
                "profile",
                BlockerKind.BLOCKED_AUTHORITY,
                "repository profile targets another tenant or repository",
            )
        if payload.get("configuration_digest") != self.manifest.configuration_digest:
            return CompositionBlocker(
                "profile",
                BlockerKind.BLOCKED_AUTHORITY,
                "composition manifest targets another configuration",
            )
        if not self.repository_profile.allows(ProfileCapability.LOCAL_BUILD):
            return CompositionBlocker(
                "builder",
                BlockerKind.BLOCKED_AUTHORITY,
                "repository profile does not grant local build",
            )
        return None

    def execute_package(
        self,
        package: OutcomeWorkPackage,
        bindings: tuple[Any, Any],
        payload: Mapping[str, Any],
    ) -> PackageExecutionResult:
        del bindings  # Resolution is performed by WholeOSService before this boundary.
        payload_digest = canonical_digest(_plain(payload))
        path = self._receipt_path(payload, package.package_id)
        retained = self._load_result(path, payload_digest)
        if retained is not None:
            return retained
        subject_blocker = self._validate_subject(payload)
        if subject_blocker is not None:
            return self._blocked(package, path, payload_digest, subject_blocker)
        if not package.acceptance_ids:
            return self._blocked(
                package,
                path,
                payload_digest,
                CompositionBlocker(
                    "qualification",
                    BlockerKind.BLOCKED_SOURCE,
                    "package has no executable acceptance manifest",
                ),
            )
        if self.delivery_policy.roblox_runtime_required:
            readiness = self.readiness()
            roblox_blocker = next(
                (
                    item
                    for item in readiness.blockers
                    if item.stage in {"roblox-profile", "roblox-runtime"}
                ),
                None,
            )
            if roblox_blocker is not None:
                return self._blocked(package, path, payload_digest, roblox_blocker)

        try:
            discovery = self.discovery.discover(package, payload)
        except CompositionError as exc:
            return self._blocked(
                package,
                path,
                payload_digest,
                CompositionBlocker("discovery", BlockerKind.BLOCKED_SOURCE, str(exc)),
            )
        try:
            build = self.builder.build(package, discovery, payload)
        except CompositionError as exc:
            return self._blocked(
                package,
                path,
                payload_digest,
                CompositionBlocker("builder", BlockerKind.BLOCKED_SOURCE, str(exc)),
            )
        disposition = build.result.disposition
        if disposition is BuilderDisposition.NEEDS_CONTRACT_AMENDMENT:
            return self._blocked(
                package,
                path,
                payload_digest,
                CompositionBlocker(
                    "builder",
                    BlockerKind.BLOCKED_AUTHORITY,
                    "builder requires a contract amendment",
                ),
            )
        if disposition in {
            BuilderDisposition.BLOCKED,
            BuilderDisposition.BUDGET_EXHAUSTED,
        }:
            return self._finish(
                path,
                payload_digest,
                PackageExecutionResult(
                    package.package_id,
                    PackageStatus.FAILED,
                    None,
                    tuple(build.result.evidence_refs),
                    f"builder:{disposition.value}",
                ),
            )

        qualification = self.qualifier.qualify(
            QualificationRequest(
                build.candidate_commit,
                _base_snapshot(payload),
                package.acceptance_ids,
                build.result.changed_paths,
                package.risk_tier,
                self.delivery_policy.qualification_sandbox_digest,
                self.delivery_policy.qualification_toolchain_digest,
                self.delivery_policy.qualification_environment_digest,
                self.delivery_policy.evaluator_id,
            )
        )
        if qualification.disposition is not QualificationDisposition.PASSED:
            return self._finish(
                path,
                payload_digest,
                PackageExecutionResult(
                    package.package_id,
                    PackageStatus.BLOCKED_CAPABILITY,
                    None,
                    (qualification.digest,),
                    "BLOCKED_CAPABILITY:qualification:independent checks did not pass",
                ),
            )

        if self.delivery_policy.publish_required and not self.repository_profile.allows(
            ProfileCapability.CODE_PR, destination=self.delivery_policy.target
        ):
            return self._blocked(
                package,
                path,
                payload_digest,
                CompositionBlocker(
                    "delivery",
                    BlockerKind.BLOCKED_AUTHORITY,
                    "repository profile does not grant code PR delivery",
                ),
            )
        request = self._delivery_request(package, payload, build, qualification)
        intent_path = path.with_suffix(".delivery-intent.json")
        intent = {
            "schema_version": 1,
            "kind": "whole-os-delivery-intent",
            "payload_digest": payload_digest,
            "request_digest": canonical_digest(request),
            "idempotency_key": request.idempotency_key,
        }
        if intent_path.exists():
            delivery = self.delivery.reconcile(request)
        else:
            self._write_once(intent_path, intent)
            delivery = self.delivery.prepare(request)
        if delivery.state is DeliveryState.RECONCILIATION_REQUIRED:
            blocker = CompositionBlocker(
                "delivery",
                BlockerKind.RECONCILIATION_REQUIRED,
                delivery.blocker or "remote delivery outcome is uncertain",
            )
            # Do not seal a terminal package result: a later bounded scheduler
            # attempt may reconcile this durable intent through transport
            # observation. DeliveryBroker never repeats the effect on this path.
            return PackageExecutionResult(
                package.package_id,
                PackageStatus.FAILED,
                None,
                (blocker.reference,),
                blocker.message,
            )
        if delivery.state is DeliveryState.BLOCKED or (
            self.delivery_policy.publish_required
            and delivery.state is not DeliveryState.PUBLISHED
        ):
            return self._blocked(
                package,
                path,
                payload_digest,
                CompositionBlocker(
                    "delivery",
                    BlockerKind.BLOCKED_AUTHORITY,
                    delivery.blocker or "required PR delivery did not publish",
                ),
            )

        observations = (
            self.feedback_source.observations(delivery, package)
            if self.feedback_source is not None
            else ()
        )
        if self.delivery_policy.feedback_required and not observations:
            return self._blocked(
                package,
                path,
                payload_digest,
                CompositionBlocker(
                    "feedback",
                    BlockerKind.BLOCKED_CAPABILITY,
                    "outcome observation adapter returned no evidence",
                ),
            )
        feedback_refs: list[str] = []
        current_head = delivery.branch_head or build.candidate_commit
        for observation in observations:
            if delivery.pr_id is None or observation.pr_id != delivery.pr_id:
                return self._blocked(
                    package,
                    path,
                    payload_digest,
                    CompositionBlocker(
                        "feedback",
                        BlockerKind.BLOCKED_SOURCE,
                        "feedback callback targets another delivery",
                    ),
                )
            decision = self.feedback.observe(observation, current_head)
            feedback_refs.extend(observation.evidence_refs)
            feedback_refs.append(canonical_digest(observation))
            if decision.decision is FeedbackDecision.STALE_HEAD:
                return self._finish(
                    path,
                    payload_digest,
                    PackageExecutionResult(
                        package.package_id,
                        PackageStatus.FAILED,
                        None,
                        tuple(dict.fromkeys(feedback_refs)),
                        "feedback:stale target head",
                    ),
                )
            if decision.decision is FeedbackDecision.AUTHORITY_CHANGE:
                return self._blocked(
                    package,
                    path,
                    payload_digest,
                    CompositionBlocker(
                        "feedback",
                        BlockerKind.BLOCKED_AUTHORITY,
                        "feedback requests an authority change",
                    ),
                )
            if decision.decision is FeedbackDecision.ACTIONABLE:
                return self._finish(
                    path,
                    payload_digest,
                    PackageExecutionResult(
                        package.package_id,
                        PackageStatus.FAILED,
                        None,
                        tuple(dict.fromkeys(feedback_refs)),
                        "feedback:qualified repair is required",
                    ),
                )

        destination_subject = (
            self.delivery_policy.learning_destination_subject_id
            or self.repository_profile.identity.repository_id
        )
        if self.delivery_policy.learning_scope is LearningScope.EXPORT_DRAFT and not (
            self.delivery_policy.learning_export_destination
            and self.repository_profile.allows(
                ProfileCapability.LEARNING_EXPORT,
                destination=self.delivery_policy.learning_export_destination,
            )
        ):
            return self._blocked(
                package,
                path,
                payload_digest,
                CompositionBlocker(
                    "learning",
                    BlockerKind.BLOCKED_AUTHORITY,
                    "repository profile does not grant sanitized learning export",
                ),
            )
        evidence = tuple(
            dict.fromkeys(
                (
                    *discovery.evidence_refs,
                    discovery.court_receipt,
                    *build.result.evidence_refs,
                    qualification.digest,
                    delivery.request_digest,
                    *feedback_refs,
                )
            )
        )
        route = LearningRoute(
            self.repository_profile.identity.repository_id,
            self.delivery_policy.learning_scope,
            destination_subject,
            evidence,
            "whole-os-package-outcome",
            self.delivery_policy.learning_authorization_digest,
            canonical_digest(
                {
                    "package_id": package.package_id,
                    "candidate_tree": build.candidate_tree,
                    "feedback": feedback_refs,
                }
            ),
        )
        learning_ref = self.learning.record(route)
        return self._finish(
            path,
            payload_digest,
            PackageExecutionResult(
                package.package_id,
                (
                    PackageStatus.NO_CHANGE
                    if disposition is BuilderDisposition.NO_CHANGE
                    else PackageStatus.COMPLETED
                ),
                build.candidate_tree,
                tuple(dict.fromkeys((*evidence, learning_ref))),
                "composed package completed",
            ),
        )

    def _delivery_request(
        self,
        package: OutcomeWorkPackage,
        payload: Mapping[str, Any],
        build: BuildOutcome,
        qualification: QualificationReceipt,
    ) -> DeliveryRequest:
        identity = {
            "campaign_id": payload["campaign_id"],
            "tenant_id": payload["tenant_id"],
            "repository_id": payload["repository_id"],
            "graph_digest": payload["graph_digest"],
            "package_id": package.package_id,
            "candidate_tree": build.candidate_tree,
        }
        operation = canonical_digest(identity)
        return DeliveryRequest(
            request_id=operation,
            package_id=package.package_id,
            tenant_id=str(payload["tenant_id"]),
            candidate_commit=build.candidate_commit,
            candidate_tree=build.candidate_tree,
            qualification_digest=qualification.digest,
            target=self.delivery_policy.target,
            base=self.delivery_policy.base,
            run_branch=(
                self.delivery_policy.run_branch_prefix.rstrip("/")
                + "/"
                + package.package_id
            ),
            grant_ref=self.delivery_policy.grant_ref,
            artifact_kind=ArtifactKind.APPLICATION,
            content_digest=canonical_digest(identity),
            idempotency_key=operation,
            changed_paths=build.result.changed_paths,
        )

    def assess_terminal_candidate(
        self, candidate: ConvergenceResult, payload: Mapping[str, Any]
    ) -> TerminalAssessment:
        frozen_payload = MappingProxyType(dict(payload))
        assessment = self.curator.assess(candidate, frozen_payload)
        if not isinstance(assessment, TerminalAssessment):
            raise CompositionError("terminal curator returned an untyped assessment")
        return assessment


__all__ = [
    "BacklogDiscoveryAdapter",
    "BlockerKind",
    "BoundedBuilderAdapter",
    "BuildOutcome",
    "CompositionBlocker",
    "CompositionError",
    "CompositionReadiness",
    "DeliveryPolicy",
    "DiscoveryAdapter",
    "DiscoveryOutcome",
    "DurableLearningRecorder",
    "FeedbackSource",
    "LearningRecorder",
    "TerminalCurator",
    "WholeOSCompositionHost",
]
