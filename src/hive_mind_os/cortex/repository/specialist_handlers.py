"""Concrete offline handlers for the bounded eight-specialist DAG.

Each native handler calls the existing role implementation directly and emits a
small canonical result.  The generic fallback is deliberately marked as
non-native; :class:`ExecutableDagRuntime` therefore fails it closed for every
native specialist node.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Callable, cast

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
        return self._handlers.get(role, self.generic_handler)

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
            },
            True,
            _NATIVE_SYMBOLS["builder"],
            _input_digests(context),
        )

    def _curator(self, context: SpecialistContext) -> SpecialistResult:
        runtime = CuratorRuntime()
        checks = ("artifact-dependency-integrity", "repository-test-presence")
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
        identity = self._candidate_identity(candidate_root)
        workspace = IsolatedCandidateWorkspace(
            "workspace:curator:v2",
            candidate_root,
            identity,
            "workspace:builder:v2",
            context.workspaces_root / "04-builder",
        )

        def check(name: str, root: Path) -> bool:
            if name == "artifact-dependency-integrity":
                return all(
                    context.artifact_for(source).envelope.artifact_digest
                    for source in context.artifacts
                )
            if name == "repository-test-presence":
                tests = root / "tests"
                return tests.is_dir() and any(tests.rglob("test_*.py"))
            return False

        report = runtime.verify(seal, workspace, candidate=identity, check_runner=check)
        if report.verdict is not CuratorVerdict.ADOPT:
            raise RuntimeError(
                "independent Curator did not adopt candidate: "
                + ", ".join(report.reasons)
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
                "candidate_scope": "committed repository HEAD; builder artifact checked separately",
            },
            True,
            _NATIVE_SYMBOLS["curator"],
            _input_digests(context),
        )

    def _integrator(self, context: SpecialistContext) -> SpecialistResult:
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
            True,
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
            },
            True,
            _NATIVE_SYMBOLS["integrator"],
            _input_digests(context),
        )

    def _steward(self, context: SpecialistContext) -> SpecialistResult:
        observations = []
        for surface in HealthSurface:
            evidence = {
                "surface": surface.value,
                "source_artifacts": list(_input_digests(context)),
                "bounded_offline_observation": True,
            }
            observations.append(
                HealthObservation(
                    surface,
                    HealthStatus.HEALTHY,
                    f"offline:{surface.value}",
                    evidence,
                    canonical_digest(evidence),
                )
            )
        report = Steward().assess(tuple(observations))
        return SpecialistResult(
            {
                "role": "steward",
                "readiness": report.readiness.value,
                "report_digest": report.report_digest,
                "observed_surfaces": [
                    value.surface.value for value in report.observations
                ],
                "limitation": "offline artifact health, not live provider or deployment health",
            },
            True,
            _NATIVE_SYMBOLS["steward"],
            _input_digests(context),
        )

    def _optimizer(self, context: SpecialistContext) -> SpecialistResult:
        optimizer = Optimizer()
        attribution = OutcomeAttribution(
            evidence_refs=_evidence_refs(context),
            context_ref=f"dag-plan:{context.plan_digest}",
            outcome_ref="outcome:offline-specialist-run",
            error_class="bounded-offline-evaluation",
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
            evidence_complete=True,
        )
        return SpecialistResult(
            {
                "role": "optimizer",
                "lesson_digest": lesson.lesson_digest,
                "challenger_proposal_digest": proposal.proposal_digest,
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

    @staticmethod
    def _candidate_identity(root: Path) -> CandidateIdentity:
        git = RepositoryExplorer._trusted_git_executable()
        completed = subprocess.run(
            (str(git), "rev-parse", "HEAD^{commit}", "HEAD^{tree}"),
            cwd=root,
            env=_git_environment(git.parent, root),
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
