"""Concrete offline handlers for the bounded eight-specialist DAG.

Each native handler calls the existing role implementation directly and emits a
small canonical result.  The generic fallback is deliberately marked as
non-native; :class:`ExecutableDagRuntime` therefore fails it closed for every
native specialist node.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from hashlib import sha256
from pathlib import Path
from typing import Callable, Mapping, cast

from ...brain_kernel.architect import (
    AcceptanceMapping,
    Architect,
    ArchitectureArtifact,
    DesignOption,
    InterfaceContract,
)
from ...brain_kernel.authority import AuthorityRegistry
from ...brain_kernel.builder import (
    BuilderAction,
    BuilderActionKind,
    BuilderCoordinator,
)
from ...brain_kernel.canonical import canonical_digest
from ...brain_kernel.contracts import (
    Budget,
    ConstraintEnvelope,
    EffectIntent,
    MissionCharter,
    MissionState,
    WorkItem,
    WorkState,
)
from ...brain_kernel.curator_runtime import (
    CandidateIdentity,
    CuratorRuntime,
    CuratorVerdict,
    IsolatedCandidateWorkspace,
)
from ...brain_kernel.dag_runtime import (
    ArtifactRequirement,
    ArtifactType,
    DagNode,
    DagPlan,
    SpecialistContext,
    SpecialistHandler,
    SpecialistResult,
)
from ...brain_kernel.effects import EffectGateway
from ...brain_kernel.explorer import RepositoryExplorer
from ...brain_kernel.integrator import (
    ContractAdapter,
    DataLineage,
    Integrator,
    VersionedContract,
)
from ...brain_kernel.optimizer import Optimizer, OutcomeAttribution
from ...brain_kernel.planner import OrchestratorPlanner, WorkSchedule
from ...brain_kernel.steward import (
    HealthObservation,
    HealthStatus,
    HealthSurface,
    Steward,
)
from .builder_adapter import IsolatedBuilderAdapter

_ZERO_DIGEST = "sha256:" + "0" * 64
_ZERO_SHA = "0" * 40
_NOW = "2030-01-01T00:00:00Z"
_EXPIRES = "2099-01-01T00:00:00Z"
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_NATIVE_SYMBOLS = {
    "orchestrator": "OrchestratorPlanner.plan",
    "explorer": "RepositoryExplorer.discover_tests",
    "architect": "Architect.produce",
    "builder": "BuilderCoordinator.repair",
    "curator": "CuratorRuntime.verify",
    "integrator": "Integrator.validate",
    "steward": "Steward.assess",
    "optimizer": "Optimizer.recommend_independent_review",
}

_CURATOR_SMOKE_TEST = "tests.test_brain_kernel_artifacts"


def repository_candidate_digest(repository_root: str | Path, plan_digest: str) -> str:
    """Bind a native specialist run to committed Git HEAD/tree and its plan.

    The working-tree path is deliberately excluded so that an independently
    reconstructed checkout has the same identity.  Callers that evaluate dirty
    or untracked files need a separate inventory binding; this native lane only
    claims the committed Git candidate.
    """

    if not isinstance(plan_digest, str) or _DIGEST.fullmatch(plan_digest) is None:
        raise ValueError("plan digest must be lowercase sha256:<64 hex>")
    root = Path(repository_root).resolve()
    identity = _repository_identity(root)
    return canonical_digest(
        {
            "schema_version": 1,
            "candidate_kind": "committed-repository-specialist-dag",
            "head_commit": identity.commit,
            "tree_oid": identity.tree,
            "plan_digest": plan_digest,
        }
    )


def _artifact_type(role: str) -> ArtifactType:
    schema_id = f"hive-mind-os/repository-specialist/{role}"
    schema_version = "1"
    return ArtifactType(
        schema_id,
        schema_version,
        canonical_digest({"schema_id": schema_id, "schema_version": schema_version}),
    )


def repository_specialist_plan(
    *, plan_id: str = "repository-specialists-v2"
) -> DagPlan:
    """Return the additive offline topology; the v1 tournament remains untouched."""

    types = {role: _artifact_type(role) for role in _NATIVE_SYMBOLS}

    def requirement(node_id: str, role: str) -> ArtifactRequirement:
        artifact = types[role]
        return ArtifactRequirement(node_id, artifact.schema_id, artifact.schema_version)

    return DagPlan(
        plan_id,
        (
            DagNode(
                "01-orchestrator",
                "orchestrator",
                "executor:orchestrator:v2",
                (),
                (),
                types["orchestrator"],
                native_symbol=_NATIVE_SYMBOLS["orchestrator"],
            ),
            DagNode(
                "02-explorer",
                "explorer",
                "executor:explorer:v2",
                ("01-orchestrator",),
                (requirement("01-orchestrator", "orchestrator"),),
                types["explorer"],
                native_symbol=_NATIVE_SYMBOLS["explorer"],
            ),
            DagNode(
                "03-architect",
                "architect",
                "executor:architect:v2",
                ("02-explorer",),
                (requirement("02-explorer", "explorer"),),
                types["architect"],
                native_symbol=_NATIVE_SYMBOLS["architect"],
            ),
            DagNode(
                "04-builder",
                "builder",
                "executor:builder:v2",
                ("03-architect",),
                (requirement("03-architect", "architect"),),
                types["builder"],
                write_scope=("candidate/builder-output.json",),
                native_symbol=_NATIVE_SYMBOLS["builder"],
            ),
            DagNode(
                "05-curator",
                "curator",
                "executor:curator:v2",
                ("04-builder",),
                (requirement("04-builder", "builder"),),
                types["curator"],
                write_scope=("candidate",),
                timeout_seconds=300,
                native_symbol=_NATIVE_SYMBOLS["curator"],
            ),
            DagNode(
                "06-integrator",
                "integrator",
                "executor:integrator:v2",
                ("05-curator",),
                (requirement("05-curator", "curator"),),
                types["integrator"],
                native_symbol=_NATIVE_SYMBOLS["integrator"],
            ),
            DagNode(
                "07-steward",
                "steward",
                "executor:steward:v2",
                ("05-curator",),
                (requirement("05-curator", "curator"),),
                types["steward"],
                native_symbol=_NATIVE_SYMBOLS["steward"],
            ),
            DagNode(
                "08-optimizer",
                "optimizer",
                "executor:optimizer:v2",
                ("06-integrator", "07-steward"),
                (
                    requirement("06-integrator", "integrator"),
                    requirement("07-steward", "steward"),
                ),
                types["optimizer"],
                native_symbol=_NATIVE_SYMBOLS["optimizer"],
            ),
        ),
    )


class RepositorySpecialistHandlers:
    """Dispatch all eight repository roles to their concrete kernel implementation."""

    def __init__(self, repository_root: str | Path) -> None:
        self.repository_root = Path(repository_root).resolve()
        if (
            not self.repository_root.is_dir()
            or not (self.repository_root / ".git").exists()
        ):
            raise ValueError(
                "repository specialist handlers require a Git working tree"
            )
        self._handlers: dict[str, SpecialistHandler] = {
            "orchestrator": self._orchestrator,
            "explorer": self._explorer,
            "architect": self._architect,
            "builder": self._builder,
            "curator": self._curator,
            "integrator": self._integrator,
            "steward": self._steward,
            "optimizer": self._optimizer,
        }

    @property
    def native_roles(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))

    def handler_for(self, role: str) -> SpecialistHandler:
        handler = self._handlers.get(role, self.generic_handler)

        def candidate_bound(context: SpecialistContext) -> SpecialistResult:
            observed = repository_candidate_digest(
                self.repository_root, context.plan_digest
            )
            if context.candidate_digest != observed:
                raise RuntimeError(
                    "native specialist candidate does not match committed "
                    "repository HEAD/tree and plan"
                )
            return cast(SpecialistResult, handler(context))

        return candidate_bound

    @staticmethod
    def generic_handler(context: SpecialistContext) -> SpecialistResult:
        """Return observable fallback evidence which never counts as native execution."""

        return SpecialistResult(
            {
                "role": context.node.role,
                "status": "generic-fallback-only",
                "limitation": "no concrete specialist implementation was invoked",
            },
            native_evidence=False,
            invoked_symbol="generic-fallback",
        )

    def _orchestrator(self, context: SpecialistContext) -> SpecialistResult:
        budget = Budget(60, 0, 0, 0, 0, 8, 8, 3)
        charter = MissionCharter(
            1,
            "MISSION-specialist-dag-v2",
            _NOW,
            "exercise all repository specialists through typed evidence",
            ("ACCEPT-specialist-evidence",),
            str(self.repository_root),
            _ZERO_SHA,
            "codex/specialist-dag-v2",
            _ZERO_DIGEST,
            _ZERO_DIGEST,
            _ZERO_DIGEST,
            budget,
            (),
            ("main", "master"),
            (),
            MissionState.CREATED,
        )
        work = WorkItem(
            "WORK-specialist-observation",
            charter.mission_id,
            None,
            0,
            "Observe repository",
            "Retain a typed repository inventory",
            "explorer",
            "R0",
            (),
            (),
            ("repository-inventory",),
            charter.acceptance_specs,
            (),
            (),
            {},
            1,
            WorkState.PROPOSED,
            _ZERO_DIGEST,
            canonical_digest({"work": "specialist-observation"}),
        )
        schedule = WorkSchedule(
            work.work_id,
            Budget(10, 0, 0, 0, 0, 2, 1, 1),
            "R0",
            ("stop on missing typed evidence",),
            ("builder", "curator"),
            (),
        )
        plan = OrchestratorPlanner().plan(charter, (work,), (schedule,))
        return SpecialistResult(
            {
                "role": "orchestrator",
                "orchestration_plan_digest": plan.digest,
                "planned_work_ids": [
                    item.work_id for item in plan.graph.ordered_items()
                ],
                "effect_authority": "none; planning only",
            },
            True,
            _NATIVE_SYMBOLS["orchestrator"],
        )

    def _explorer(self, context: SpecialistContext) -> SpecialistResult:
        explorer = RepositoryExplorer(self.repository_root)
        tests = explorer.discover_tests()
        tracked_count, tracked_receipt_digest = self._tracked_file_count()
        return SpecialistResult(
            {
                "role": "explorer",
                "tracked_file_count": tracked_count,
                "test_file_count": len(tests),
                "tracked_files_receipt_digest": tracked_receipt_digest,
                "trust_boundary": "untrusted-command-output",
                "sample_tests": list(tests[:20]),
            },
            True,
            _NATIVE_SYMBOLS["explorer"],
            _input_digests(context),
        )

    def _architect(self, context: SpecialistContext) -> SpecialistResult:
        artifact = ArchitectureArtifact(
            objective="Execute specialists through typed, dependency-bound evidence.",
            options=(
                DesignOption(
                    "dependency-ready-dag",
                    "Run ready specialists concurrently with central evidence ordering.",
                    ("in-process handlers are cooperative rather than OS sandboxed",),
                ),
                DesignOption(
                    "serial-pipeline",
                    "Run one specialist at a time.",
                    ("independent branches cannot overlap",),
                ),
            ),
            selected_option="dependency-ready-dag",
            interfaces=(
                InterfaceContract(
                    "typed-artifact-edge",
                    "specialist producer",
                    "dependent specialist",
                    "immutable content-addressed ArtifactEnvelope",
                    "schema id and version must match exactly",
                ),
            ),
            invariants=(
                "Every role executes once under a unique executor identity.",
                "A failed node blocks descendants but not unrelated peers.",
            ),
            threats=(
                "In-process code can bypass cooperative workspace helpers.",
                "Completion timing could contaminate evidence order.",
            ),
            data_classification=("local repository metadata",),
            compatibility_impact="Additive v2 modules; sealed v1 artifacts remain unchanged.",
            migration_plan="Adopt only through explicit repository_specialist_plan callers.",
            rollback_plan="Remove the additive v2 call site and retain adverse receipts.",
            acceptance_mappings=(
                AcceptanceMapping(
                    "typed-dependencies",
                    ("typed-artifact-edge",),
                    ("test_typed_dependency_mismatch_fails_closed",),
                ),
                AcceptanceMapping(
                    "rollback",
                    ("rollback_plan",),
                    ("test_runtime_preserves_peer_failures",),
                ),
            ),
        )
        produced = Architect().produce(
            artifact, sealed_criteria=("typed-dependencies", "rollback")
        )
        return SpecialistResult(
            {
                "role": "architect",
                "architecture_digest": produced.digest,
                "selected_option": produced.selected_option,
                "unknowns": list(produced.unknowns),
            },
            True,
            _NATIVE_SYMBOLS["architect"],
            _input_digests(context),
        )

    def _builder(self, context: SpecialistContext) -> SpecialistResult:
        target = "candidate/builder-output.json"
        envelope = ConstraintEnvelope(
            "AUTH-specialist-builder",
            "MISSION-specialist-dag-v2",
            "WORK-specialist-builder",
            None,
            "builder",
            "R1",
            ("write", "command"),
            ("push", "merge", "deploy", "network"),
            ("isolated-workspace",),
            ("candidate", "isolated-workspace"),
            (),
            (),
            (),
            (),
            Budget(30, 0, 0, 0, 0, 2, 1, 1),
            _EXPIRES,
            canonical_digest({"policy": "specialist-builder-v2"}),
            _ZERO_DIGEST,
        ).sealed()
        authority = AuthorityRegistry()
        authority.mint_root(
            envelope,
            issuer="owner:offline-specialist-runtime",
            authority_ref="authority:offline-specialist-runtime",
            recorded_at=_NOW,
        )
        adapter = IsolatedBuilderAdapter(context.workspace)
        gateway = EffectGateway(authority=authority, clock=lambda: _NOW)
        gateway.register_adapter(
            adapter.adapter_name,
            cast(Callable[[EffectIntent], object], adapter.apply),
        )
        coordinator = BuilderCoordinator(
            gateway,
            authority,
            adapter,
            mission_id="MISSION-specialist-dag-v2",
            work_id="WORK-specialist-builder",
            actor_id=context.node.executor_id,
            authority_envelope_digest=envelope.digest_value,
            policy_decision_ref="policy:offline-specialist-runtime",
            now=_NOW,
        )
        content = (
            '{"architecture_artifact":"'
            + context.artifact_for("03-architect").envelope.artifact_digest
            + '","status":"built-in-isolated-fixture"}\n'
        )
        actions = (
            BuilderAction(
                "write-specialist-output",
                BuilderActionKind.WRITE,
                target,
                {"content": content},
                "remove the isolated builder output",
            ),
            BuilderAction(
                "check-specialist-output",
                BuilderActionKind.COMMAND,
                "isolated-workspace",
                {"profile": "file-exists", "paths": (target,)},
                "no mutation to roll back",
            ),
        )
        executions = coordinator.repair((actions,), max_retries=0)
        if any(value.outcome.status != "SUCCEEDED" for value in executions):
            raise RuntimeError("bounded Builder action did not succeed")
        product = context.confined_path(target)
        try:
            product_digest = _bytes_digest(product.read_bytes())
        except OSError as error:
            raise RuntimeError("bounded Builder product is unavailable") from error
        return SpecialistResult(
            {
                "role": "builder",
                "actions": [
                    {
                        "action_id": value.action.action_id,
                        "status": value.outcome.status,
                        "effect_receipt_digest": value.effect.receipt_digest,
                        "output_digest": value.outcome.output_digest,
                    }
                    for value in executions
                ],
                "workspace_product": target,
                "workspace_product_digest": product_digest,
            },
            True,
            _NATIVE_SYMBOLS["builder"],
            _input_digests(context),
        )

    def _curator(self, context: SpecialistContext) -> SpecialistResult:
        runtime = CuratorRuntime()
        checks = (
            "builder-artifact-and-product",
            "repository-test-presence",
            "repository-nonrecursive-smoke",
        )
        seal = runtime.seal_acceptance(
            mission_id="MISSION-specialist-dag-v2",
            work_id="WORK-specialist-curator",
            curator_id=context.node.executor_id,
            checks=checks,
            failure_verdict=CuratorVerdict.REMAND,
        )
        # Candidate materialization deliberately happens only after the blind seal.
        candidate_root = context.confined_path("candidate")
        self._clone_candidate(candidate_root)
        identity = _repository_identity(candidate_root)
        if (
            repository_candidate_digest(candidate_root, context.plan_digest)
            != context.candidate_digest
        ):
            raise RuntimeError(
                "Curator clone does not match the committed candidate binding"
            )
        workspace = IsolatedCandidateWorkspace(
            "workspace:curator:v2",
            candidate_root,
            identity,
            "workspace:builder:v2",
            context.workspaces_root / "04-builder",
        )

        builder_validation: dict[str, object] = {
            "passed": False,
            "error_type": "not-run",
        }
        test_presence: dict[str, object] = {
            "passed": False,
            "pattern": "tests/test_*.py",
        }
        smoke_test: dict[str, object] = _not_run_smoke_evidence()

        def check(name: str, root: Path) -> bool:
            nonlocal builder_validation, test_presence, smoke_test
            if name == "builder-artifact-and-product":
                try:
                    builder_validation = _validate_builder_handoff(context)
                except (OSError, TypeError, ValueError) as error:
                    builder_validation = {
                        "passed": False,
                        "error_type": type(error).__name__,
                    }
                return builder_validation.get("passed") is True
            if name == "repository-test-presence":
                tests = root / "tests"
                passed = tests.is_dir() and any(tests.rglob("test_*.py"))
                test_presence = {
                    "passed": passed,
                    "pattern": "tests/test_*.py",
                }
                return passed
            if name == "repository-nonrecursive-smoke":
                with tempfile.TemporaryDirectory(
                    prefix=".curator-smoke-", dir=context.workspace
                ) as temporary:
                    smoke_test = _run_curator_smoke(root, Path(temporary))
                return smoke_test.get("passed") is True
            return False

        report = runtime.verify(seal, workspace, candidate=identity, check_runner=check)
        if report.verdict is not CuratorVerdict.ADOPT:
            diagnostic_digest = canonical_digest(
                {
                    "report_digest": report.report_digest,
                    "builder_validation": builder_validation,
                    "test_presence": test_presence,
                    "smoke_test": smoke_test,
                    "reasons": report.reasons,
                }
            )
            raise RuntimeError(
                "bounded Curator remanded candidate; diagnostic=" + diagnostic_digest
            )
        return SpecialistResult(
            {
                "role": "curator",
                "seal_digest": seal.seal_digest,
                "candidate_commit": identity.commit,
                "candidate_tree": identity.tree,
                "report_digest": report.report_digest,
                "verdict": report.verdict.value,
                "check_results": [list(value) for value in report.check_results],
                "builder_validation": builder_validation,
                "test_presence": test_presence,
                "smoke_test": smoke_test,
                "candidate_scope": (
                    "committed repository HEAD; Builder artifact and product "
                    "validated as a separate bounded handoff"
                ),
            },
            True,
            _NATIVE_SYMBOLS["curator"],
            _input_digests(context),
        )

    def _integrator(self, context: SpecialistContext) -> SpecialistResult:
        curator = _curator_payload(context)
        curator_complete = _curator_evidence_complete(curator)
        source = VersionedContract(
            "repository-specialist-artifact",
            1,
            "brain-kernel-v2",
            canonical_digest({"contract": "repository-specialist", "version": 1}),
            DataLineage(
                "artifact:architecture",
                (),
                _evidence_refs(context),
            ),
        )
        target = VersionedContract(
            "repository-specialist-artifact",
            2,
            "repository-cortex-v2",
            canonical_digest({"contract": "repository-specialist", "version": 2}),
            DataLineage(
                "artifact:integration",
                (source.lineage.artifact_id,),
                _evidence_refs(context),
            ),
        )
        adapter = ContractAdapter(
            "adapter:repository-specialist-v1-v2",
            source.identity,
            target.identity,
            _evidence_refs(context),
            curator_complete,
        )
        report = Integrator().validate(
            source, target, adapter, accepted_consumer_versions=(2,)
        )
        return SpecialistResult(
            {
                "role": "integrator",
                "status": report.status.value,
                "compatibility_report_digest": report.digest,
                "lineage_digest": report.lineage_digest,
                "findings": list(report.findings),
                "builder_remands": [value.work_id for value in report.builder_remands],
                "curator_evidence_complete": curator_complete,
            },
            True,
            _NATIVE_SYMBOLS["integrator"],
            _input_digests(context),
        )

    def _steward(self, context: SpecialistContext) -> SpecialistResult:
        curator = _curator_payload(context)
        complete = _curator_evidence_complete(curator)
        observed_surfaces = {
            HealthSurface.RECEIPTS,
            HealthSurface.SNAPSHOTS,
            HealthSurface.WORKSPACES,
        }
        observations = []
        for surface in HealthSurface:
            observed = surface in observed_surfaces
            status = (
                HealthStatus.HEALTHY
                if observed and complete
                else HealthStatus.CRITICAL
                if observed
                else HealthStatus.DEGRADED
            )
            evidence = {
                "surface": surface.value,
                "source_artifacts": list(_input_digests(context)),
                "bounded_offline_observation": observed,
                "curator_verdict": curator["verdict"],
                "derived_status": status.value,
            }
            observations.append(
                HealthObservation(
                    surface,
                    status,
                    f"offline:{surface.value}",
                    evidence,
                    canonical_digest(evidence),
                    None
                    if status is HealthStatus.HEALTHY
                    else f"reobserve:{surface.value}:external-runtime",
                )
            )
        report = Steward().assess(tuple(observations))
        statuses = {
            value.surface.value: value.status.value for value in report.observations
        }
        return SpecialistResult(
            {
                "role": "steward",
                "readiness": report.readiness.value,
                "report_digest": report.report_digest,
                "surface_statuses": statuses,
                "observed_surfaces": sorted(
                    surface.value for surface in observed_surfaces
                ),
                "unobserved_surfaces": sorted(
                    surface.value
                    for surface in HealthSurface
                    if surface not in observed_surfaces
                ),
                "limitation": (
                    "receipt, snapshot, and workspace status derives from the "
                    "bounded Curator artifact; queues, leases, event chains, and "
                    "providers are explicitly unobserved"
                ),
            },
            True,
            _NATIVE_SYMBOLS["steward"],
            _input_digests(context),
        )

    def _optimizer(self, context: SpecialistContext) -> SpecialistResult:
        integrator = _strict_artifact_payload(
            context,
            "06-integrator",
            {
                "role",
                "status",
                "compatibility_report_digest",
                "lineage_digest",
                "findings",
                "builder_remands",
                "curator_evidence_complete",
            },
            "Integrator",
        )
        steward = _strict_artifact_payload(
            context,
            "07-steward",
            {
                "role",
                "readiness",
                "report_digest",
                "surface_statuses",
                "observed_surfaces",
                "unobserved_surfaces",
                "limitation",
            },
            "Steward",
        )
        integrator_complete = (
            integrator.get("role") == "integrator"
            and integrator.get("status") == "compatible"
            and integrator.get("curator_evidence_complete") is True
            and integrator.get("builder_remands") == []
        )
        surface_statuses = steward.get("surface_statuses")
        steward_complete = (
            steward.get("role") == "steward"
            and steward.get("readiness") == "ready"
            and steward.get("unobserved_surfaces") == []
            and isinstance(surface_statuses, dict)
            and set(surface_statuses.values()) == {"healthy"}
        )
        evidence_complete = integrator_complete and steward_complete
        completeness_reasons = []
        if not integrator_complete:
            completeness_reasons.append("integration-or-Curator-evidence-is-incomplete")
        if not steward_complete:
            completeness_reasons.append(
                "operational-surfaces-are-unobserved-or-unhealthy"
            )
        optimizer = Optimizer()
        attribution = OutcomeAttribution(
            evidence_refs=_evidence_refs(context),
            context_ref=f"dag-plan:{context.plan_digest}",
            outcome_ref="outcome:offline-specialist-run",
            error_class=(
                "bounded-offline-evaluation"
                if evidence_complete
                else "incomplete-operational-observation"
            ),
            applicability=("repository-specialists", "typed-dag"),
            confidence=0.75,
            expires_at=_EXPIRES,
            provenance_ref=f"candidate:{context.candidate_digest}",
        )
        lesson = optimizer.attribute_outcome(attribution)
        proposal = optimizer.propose_challenger(
            lesson,
            challenger_id="candidate:repository-specialists:v2-next",
            champion_id="candidate:repository-specialists:v2",
            change_ref=f"lesson:{lesson.lesson_digest}",
            author_id=context.node.executor_id,
        )
        recommendation = optimizer.recommend_independent_review(
            proposal,
            evaluator_id="executor:curator:v2",
            evidence_complete=evidence_complete,
        )
        return SpecialistResult(
            {
                "role": "optimizer",
                "lesson_digest": lesson.lesson_digest,
                "challenger_proposal_digest": proposal.proposal_digest,
                "evidence_complete": evidence_complete,
                "completeness_reasons": completeness_reasons,
                "recommendation": recommendation.recommendation.value,
                "promotion_effect": "none; independent court review is still required",
            },
            True,
            _NATIVE_SYMBOLS["optimizer"],
            _input_digests(context),
        )

    def _clone_candidate(self, target: Path) -> None:
        if target.exists():
            raise RuntimeError("Curator candidate workspace must be fresh")
        git = RepositoryExplorer._trusted_git_executable()
        environment = _git_environment(git.parent, target.parent)
        completed = subprocess.run(
            (
                str(git),
                "-c",
                "credential.helper=",
                "-c",
                "core.hooksPath=",
                "-c",
                "core.symlinks=false",
                "clone",
                "--quiet",
                "--local",
                "--no-hardlinks",
                str(self.repository_root),
                str(target),
            ),
            cwd=target.parent,
            env=environment,
            shell=False,
            check=False,
            capture_output=True,
            timeout=180,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "local candidate reconstruction failed: "
                + canonical_digest({"stderr": completed.stderr.hex()})
            )

    def _tracked_file_count(self) -> tuple[int, str]:
        git = RepositoryExplorer._trusted_git_executable()
        completed = subprocess.run(
            (str(git), "ls-files", "--cached", "-z"),
            cwd=self.repository_root,
            env=_git_environment(git.parent, self.repository_root),
            shell=False,
            check=False,
            capture_output=True,
            timeout=30,
        )
        if completed.returncode != 0:
            raise RuntimeError("trusted Git tracked-file observation failed")
        paths = tuple(value for value in completed.stdout.split(b"\0") if value)
        return len(paths), canonical_digest(
            {
                "argv": (str(git), "ls-files", "--cached", "-z"),
                "returncode": completed.returncode,
                "stdout_digest": canonical_digest({"bytes": completed.stdout.hex()}),
                "stderr_digest": canonical_digest({"bytes": completed.stderr.hex()}),
                "trust_boundary": "untrusted-command-output",
            }
        )


def _repository_identity(root: Path) -> CandidateIdentity:
    repository = root.resolve()
    if not repository.is_dir() or not (repository / ".git").exists():
        raise RuntimeError("candidate Git repository is unavailable")
    git = RepositoryExplorer._trusted_git_executable()
    completed = subprocess.run(
        (str(git), "rev-parse", "HEAD^{commit}", "HEAD^{tree}"),
        cwd=repository,
        env=_git_environment(git.parent, repository),
        shell=False,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=30,
    )
    values = completed.stdout.splitlines()
    if completed.returncode != 0 or len(values) != 2:
        raise RuntimeError("candidate Git identity is unavailable")
    return CandidateIdentity(values[0], values[1])


def _bytes_digest(content: bytes) -> str:
    return f"sha256:{sha256(content).hexdigest()}"


def _reject_duplicate_json_pairs(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("specialist artifact contains duplicate JSON keys")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _strict_json_object(
    content: bytes, expected_fields: set[str], label: str
) -> dict[str, object]:
    try:
        value = json.loads(
            content.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_json_pairs,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{label} artifact is not strict JSON") from error
    if not isinstance(value, dict) or set(value) != expected_fields:
        raise ValueError(f"{label} artifact fields are invalid")
    return value


def _strict_artifact_payload(
    context: SpecialistContext,
    producer_node_id: str,
    expected_fields: set[str],
    label: str,
) -> dict[str, object]:
    return _strict_json_object(
        context.artifact_for(producer_node_id).content,
        expected_fields,
        label,
    )


def _validate_builder_handoff(context: SpecialistContext) -> dict[str, object]:
    stored = context.artifact_for("04-builder")
    payload = _strict_json_object(
        stored.content,
        {
            "role",
            "actions",
            "workspace_product",
            "workspace_product_digest",
        },
        "Builder",
    )
    if payload["role"] != "builder":
        raise ValueError("Builder artifact role is invalid")
    actions = payload["actions"]
    if not isinstance(actions, list) or len(actions) != 2:
        raise ValueError("Builder artifact action evidence is incomplete")
    expected_action_ids = {
        "write-specialist-output",
        "check-specialist-output",
    }
    observed_action_ids: set[str] = set()
    receipt_digests: list[str] = []
    for action in actions:
        if not isinstance(action, Mapping) or set(action) != {
            "action_id",
            "status",
            "effect_receipt_digest",
            "output_digest",
        }:
            raise ValueError("Builder action evidence fields are invalid")
        action_id = action["action_id"]
        if not isinstance(action_id, str):
            raise ValueError("Builder action identity is invalid")
        observed_action_ids.add(action_id)
        if action["status"] != "SUCCEEDED":
            raise ValueError("Builder action did not succeed")
        for key in ("effect_receipt_digest", "output_digest"):
            digest = action[key]
            if not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None:
                raise ValueError("Builder action digest is invalid")
        receipt_digests.append(cast(str, action["effect_receipt_digest"]))
    if observed_action_ids != expected_action_ids:
        raise ValueError("Builder action evidence is incomplete")

    product_relative = payload["workspace_product"]
    if product_relative != "candidate/builder-output.json":
        raise ValueError("Builder product path is not the sealed target")
    claimed_product_digest = payload["workspace_product_digest"]
    if (
        not isinstance(claimed_product_digest, str)
        or _DIGEST.fullmatch(claimed_product_digest) is None
    ):
        raise ValueError("Builder product digest is invalid")
    builder_root = (context.workspaces_root / "04-builder").resolve()
    product_path = builder_root.joinpath(*cast(str, product_relative).split("/"))
    resolved_product = product_path.resolve(strict=True)
    try:
        resolved_product.relative_to(builder_root)
    except ValueError as error:
        raise ValueError("Builder product escapes its workspace") from error
    if product_path.is_symlink() or not resolved_product.is_file():
        raise ValueError("Builder product is not a regular confined file")
    product_bytes = resolved_product.read_bytes()
    product_digest = _bytes_digest(product_bytes)
    if product_digest != claimed_product_digest:
        raise ValueError("Builder product digest does not match its artifact")
    product = _strict_json_object(
        product_bytes,
        {"architecture_artifact", "status"},
        "Builder product",
    )
    dependencies = stored.envelope.dependency_digests
    if len(dependencies) != 1 or product["architecture_artifact"] != dependencies[0]:
        raise ValueError("Builder product does not bind its architecture dependency")
    if product["status"] != "built-in-isolated-fixture":
        raise ValueError("Builder product status is invalid")
    return {
        "passed": True,
        "builder_artifact_digest": stored.envelope.artifact_digest,
        "product_path": product_relative,
        "product_digest": product_digest,
        "architecture_artifact_digest": dependencies[0],
        "action_receipt_digests": sorted(receipt_digests),
        "error_type": None,
    }


def _not_run_smoke_evidence() -> dict[str, object]:
    empty = _bytes_digest(b"")
    return {
        "check_id": "repository-nonrecursive-smoke",
        "module": _CURATOR_SMOKE_TEST,
        "argv": ["python", "-B", "-m", "unittest", _CURATOR_SMOKE_TEST],
        "passed": False,
        "returncode": None,
        "tests_run": 0,
        "stdout_digest": empty,
        "stderr_digest": empty,
        "error_type": "not-run",
    }


def _curator_test_environment(repository: Path, runtime: Path) -> dict[str, str]:
    environment: dict[str, str] = {}
    for key in ("COMSPEC", "PATHEXT", "SYSTEMROOT", "WINDIR"):
        value = os.environ.get(key)
        if value and "\n" not in value and "\r" not in value:
            environment[key] = value
    runtime_text = str(runtime.resolve())
    environment.update(
        {
            "HOME": runtime_text,
            "USERPROFILE": runtime_text,
            "TEMP": runtime_text,
            "TMP": runtime_text,
            "TMPDIR": runtime_text,
            "PYTHONPATH": os.pathsep.join(
                (str((repository / "src").resolve()), str(repository.resolve()))
            ),
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONSAFEPATH": "1",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    return environment


def _run_curator_smoke(repository: Path, runtime: Path) -> dict[str, object]:
    logical_argv = ["python", "-B", "-m", "unittest", _CURATOR_SMOKE_TEST]
    arguments = [sys.executable, *logical_argv[1:]]
    try:
        completed = subprocess.run(
            arguments,
            cwd=repository,
            env=_curator_test_environment(repository, runtime),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            check=False,
            timeout=60,
        )
        output = completed.stdout + b"\n" + completed.stderr
        match = re.search(rb"Ran\s+(\d+)\s+tests?", output)
        tests_run = int(match.group(1)) if match is not None else 0
        return {
            "check_id": "repository-nonrecursive-smoke",
            "module": _CURATOR_SMOKE_TEST,
            "argv": logical_argv,
            "passed": completed.returncode == 0 and tests_run > 0,
            "returncode": completed.returncode,
            "tests_run": tests_run,
            "stdout_digest": _bytes_digest(completed.stdout),
            "stderr_digest": _bytes_digest(completed.stderr),
            "error_type": None,
        }
    except (OSError, subprocess.TimeoutExpired) as error:
        evidence = _not_run_smoke_evidence()
        evidence["returncode"] = (
            124 if isinstance(error, subprocess.TimeoutExpired) else 126
        )
        evidence["error_type"] = type(error).__name__
        return evidence


_CURATOR_ARTIFACT_FIELDS = {
    "role",
    "seal_digest",
    "candidate_commit",
    "candidate_tree",
    "report_digest",
    "verdict",
    "check_results",
    "builder_validation",
    "test_presence",
    "smoke_test",
    "candidate_scope",
}


def _curator_payload(context: SpecialistContext) -> dict[str, object]:
    payload = _strict_artifact_payload(
        context,
        "05-curator",
        _CURATOR_ARTIFACT_FIELDS,
        "Curator",
    )
    if payload["role"] != "curator":
        raise ValueError("Curator artifact role is invalid")
    return payload


def _curator_evidence_complete(payload: Mapping[str, object]) -> bool:
    check_results = payload.get("check_results")
    builder = payload.get("builder_validation")
    presence = payload.get("test_presence")
    smoke = payload.get("smoke_test")
    expected_checks = {
        "builder-artifact-and-product",
        "repository-test-presence",
        "repository-nonrecursive-smoke",
    }
    observed_checks: dict[str, bool] = {}
    if isinstance(check_results, list):
        for value in check_results:
            if (
                isinstance(value, list)
                and len(value) == 2
                and isinstance(value[0], str)
                and type(value[1]) is bool
            ):
                observed_checks[value[0]] = value[1]
    return (
        payload.get("verdict") == CuratorVerdict.ADOPT.value
        and set(observed_checks) == expected_checks
        and all(observed_checks.values())
        and isinstance(builder, Mapping)
        and builder.get("passed") is True
        and isinstance(presence, Mapping)
        and presence.get("passed") is True
        and isinstance(smoke, Mapping)
        and smoke.get("passed") is True
        and isinstance(smoke.get("tests_run"), int)
        and cast(int, smoke["tests_run"]) > 0
    )


def _input_digests(context: SpecialistContext) -> tuple[str, ...]:
    return tuple(
        sorted(value.envelope.artifact_digest for value in context.artifacts.values())
    )


def _evidence_refs(context: SpecialistContext) -> tuple[str, ...]:
    return tuple(f"artifact:{value}" for value in _input_digests(context))


def _git_environment(executable_root: Path, runtime_root: Path) -> dict[str, str]:
    environment: dict[str, str] = {}
    for key in ("COMSPEC", "PATHEXT", "SYSTEMROOT", "WINDIR"):
        value = os.environ.get(key)
        if value and "\n" not in value and "\r" not in value:
            environment[key] = value
    environment.update(
        {
            "PATH": str(executable_root),
            "HOME": str(runtime_root),
            "USERPROFILE": str(runtime_root),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_OPTIONAL_LOCKS": "0",
        }
    )
    return environment


__all__ = (
    "RepositorySpecialistHandlers",
    "repository_candidate_digest",
    "repository_specialist_plan",
)
