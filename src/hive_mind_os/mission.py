"""Local repository mission orchestration for the P05 vertical slice.

The mission composes the model boundary, typed Git adapter, process sandbox, policy
engine, append-only ledger, and fixed autonomy budget.  It intentionally remains local:
remote repositories, credentials, pushes, pull requests, resume, and hard hostile-code
isolation belong to later phases.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, TypeVar
from uuid import uuid4

from .autonomy import AutonomyBudget, BudgetExceeded, EpisodeAllowance
from .git_adapter import (
    GitPolicyDenied,
    GitWorkspace,
    verify_delivery,
)
from .ledger import EvidenceLedger
from .models import (
    AgentResult,
    AutonomyLevel,
    Evidence,
    Objective,
    Role,
    RunReport,
    WorkItem,
    WorkStatus,
    utc_now,
)
from .policy import Action, PolicyEngine
from .receipts import FileReceiptValidator, ReceiptReference
from .roles import DEFAULT_LIFECYCLE, ROLE_CONTRACTS, RoleContract
from .runtime import AgentBackend, HiveKernel

_T = TypeVar("_T")
_GOOD_FIX = b"def increment(value: int) -> int:\n    return value + 1\n"
_SABOTAGE_TEST = (
    b"import unittest\n\n"
    b"from tiny_pkg.maths import increment\n\n\n"
    b"class MathsTests(unittest.TestCase):\n"
    b"    def test_increment_regression(self) -> None:\n"
    b"        self.assertEqual(increment(1), 0)\n\n\n"
    b"if __name__ == \"__main__\":\n"
    b"    unittest.main()\n"
)
_DEFAULT_TEST_ARGV = (
    sys.executable,
    "-B",
    "-m",
    "unittest",
    "discover",
    "-s",
    "tests",
    "-v",
)
_DEFAULT_CRITERION_ARGV = (
    sys.executable,
    "-B",
    "-c",
    (
        "from tiny_pkg.maths import increment; "
        "assert increment(1) == 2, 'increment acceptance criterion failed'"
    ),
)


class MissionFailed(RuntimeError):
    """Raised internally when a mission must stop without publishing an artifact."""


@dataclass(frozen=True, slots=True)
class MissionReport(RunReport):
    """Machine-readable evidence index for one repository delivery attempt."""

    objective: str
    repository: str
    base_sha: str | None
    branch: str | None
    head_sha: str | None
    tree_digest: str | None
    artifact_directory: str | None
    receipt_root: str | None
    receipts: tuple[dict[str, Any], ...]
    curator_verdict: str
    budget_consumption: dict[str, int | float]
    event_types: tuple[str, ...]
    ledger_events: tuple[dict[str, Any], ...]
    builder_workspace: str | None
    curator_workspace: str | None
    context_manifests: tuple[dict[str, Any], ...]
    failure: dict[str, str] | None

    def to_dict(self, *, normalize_volatile: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": 1,
            "run_id": self.run_id,
            "objective_id": self.objective_id,
            "objective": self.objective,
            "repository": self.repository,
            "status": self.status.value,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "roles": [result.role.value for result in self.results],
            "results": [
                {
                    "role": result.role.value,
                    "summary": result.summary,
                    "success": result.success,
                    "evidence": [
                        {
                            "kind": evidence.kind,
                            "summary": evidence.summary,
                            "source": evidence.source,
                            "payload": evidence.payload,
                        }
                        for evidence in result.evidence
                    ],
                }
                for result in self.results
            ],
            "base_sha": self.base_sha,
            "branch": self.branch,
            "head_sha": self.head_sha,
            "tree_digest": self.tree_digest,
            "artifact_directory": self.artifact_directory,
            "receipt_root": self.receipt_root,
            "receipts": [dict(record) for record in self.receipts],
            "curator_verdict": self.curator_verdict,
            "budget_consumption": dict(self.budget_consumption),
            "event_types": list(self.event_types),
            "ledger_events": [dict(event) for event in self.ledger_events],
            "builder_workspace": self.builder_workspace,
            "curator_workspace": self.curator_workspace,
            "context_manifests": [dict(item) for item in self.context_manifests],
            "failure": self.failure,
        }
        if not normalize_volatile:
            return payload
        payload["run_id"] = "<run-id>"
        payload["objective_id"] = "<objective-id>"
        payload["started_at"] = "<timestamp>"
        payload["completed_at"] = "<timestamp>"
        payload["repository"] = "<repository>"
        payload["artifact_directory"] = (
            "<artifact-directory>" if self.artifact_directory else None
        )
        payload["receipt_root"] = "<receipt-root>" if self.receipt_root else None
        payload["builder_workspace"] = (
            "<builder-workspace>" if self.builder_workspace else None
        )
        payload["curator_workspace"] = (
            "<curator-workspace>" if self.curator_workspace else None
        )
        payload["ledger_events"] = {
            "count": len(payload["ledger_events"]),
            "actors": sorted(
                {event["actor"] for event in payload["ledger_events"]}
            ),
            "payloads": "<append-only-ledger-events>",
        }
        receipt_inventory: list[dict[str, Any]] = []
        for record in payload["receipts"]:
            key = (
                record["actor_id"],
                record["action_kind"],
                record["result"],
            )
            if receipt_inventory and (
                receipt_inventory[-1]["actor_id"],
                receipt_inventory[-1]["action_kind"],
                receipt_inventory[-1]["result"],
            ) == key:
                receipt_inventory[-1]["count"] += 1
            else:
                receipt_inventory.append(
                    {
                        "actor_id": key[0],
                        "action_kind": key[1],
                        "result": key[2],
                        "count": 1,
                        "path": "<content-addressed-receipt>",
                        "digest": "<sha256>",
                        "bindings": "<mission-state-actor-action>",
                    }
                )
        payload["receipts"] = receipt_inventory
        for result in payload["results"]:
            for evidence in result["evidence"]:
                evidence["payload"] = _normalize_payload(evidence["payload"])
        for manifest in payload["context_manifests"]:
            manifest.pop("summaries", None)
            manifest["receipt_digests"] = (
                ["<receipt-digests>"] if manifest["receipt_digests"] else []
            )
        return payload


def _normalize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                (["<receipt-digests>"] if item else [])
                if key == "receipt_digests" and isinstance(item, list)
                else _normalize_payload(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_normalize_payload(item) for item in value]
    return value


def _encoded_action(action: str, **payload: Any) -> str:
    return json.dumps(
        {"action": action, **payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


class ScriptedRepositoryBackend:
    """Deterministic offline repository backend used by CI and the fixture CLI path."""

    def __init__(
        self,
        variant: str = "good",
        *,
        test_argv: Sequence[str] = _DEFAULT_TEST_ARGV,
        criterion_argv: Sequence[str] = _DEFAULT_CRITERION_ARGV,
    ) -> None:
        if variant not in {"good", "sabotage"}:
            raise ValueError("scripted variant must be good or sabotage")
        self.variant = variant
        self.test_argv = tuple(test_argv)
        self.criterion_argv = tuple(criterion_argv)
        self.contexts: dict[Role, list[dict[str, Any]]] = {
            role: [] for role in DEFAULT_LIFECYCLE
        }

    async def execute(
        self,
        contract: RoleContract,
        work_item: WorkItem,
        objective: Objective,
        context: tuple[AgentResult, ...],
    ) -> AgentResult:
        self.contexts[contract.role].append(
            {
                "roles": [item.role.value for item in context],
                "summaries": [item.summary for item in context],
                "evidence": [
                    [
                        {
                            "kind": evidence.kind,
                            "summary": evidence.summary,
                            "source": evidence.source,
                            "payload": evidence.payload,
                        }
                        for evidence in item.evidence
                    ]
                    for item in context
                ],
            }
        )
        proposed_actions: tuple[str, ...] = ()
        if contract.role is Role.EXPLORER:
            proposed_actions = (
                _encoded_action("run_tests", argv=list(self.test_argv)),
            )
        elif contract.role is Role.BUILDER:
            if self.variant == "good":
                path, content = "tiny_pkg/maths.py", _GOOD_FIX
            else:
                path, content = "tests/test_maths.py", _SABOTAGE_TEST
            proposed_actions = (
                _encoded_action("create_branch", name="phase/mission-delivery"),
                _encoded_action(
                    "write_file",
                    path=path,
                    content_base64=base64.b64encode(content).decode("ascii"),
                ),
                _encoded_action("run_tests", argv=list(self.test_argv)),
                _encoded_action(
                    "commit",
                    message="fix: satisfy repository objective",
                ),
            )
        elif contract.role is Role.CURATOR:
            proposed_actions = (
                _encoded_action("run_tests", argv=list(self.test_argv)),
                _encoded_action(
                    "run_criterion",
                    argv=list(self.criterion_argv),
                ),
                _encoded_action("verify_delivery"),
            )
        return AgentResult(
            role=contract.role,
            work_item_id=work_item.id,
            summary=f"{contract.role.value} completed the scripted repository contract",
            evidence=tuple(
                Evidence(
                    kind="contract-output",
                    summary=name,
                    source=f"scripted-repository:{contract.role.value}",
                    payload={
                        "objective": objective.goal,
                        "context_roles": [item.role.value for item in context],
                    },
                )
                for name in contract.required_outputs
            ),
            proposed_actions=proposed_actions,
            lessons=(f"repository contract exercised for {contract.role.value}",),
        )


class _CapabilityBase:
    def __init__(
        self,
        mission: RepositoryMission,
        role: Role,
        workspace: GitWorkspace,
    ) -> None:
        self.mission = mission
        self.role = role
        self.workspace = workspace

    def _authorize(self, action: Action) -> None:
        self.mission._authorize(self.role, action)

    def _call(
        self,
        action: Action,
        expected_calls: int,
        operation: Callable[[], _T],
    ) -> tuple[_T, tuple[dict[str, Any], ...]]:
        self._authorize(action)
        return self.mission._workspace_call(
            self.workspace,
            expected_calls,
            operation,
        )


class ExplorerCapabilities(_CapabilityBase):
    """Read-only repository workspace plus receipted test discovery."""

    def run_tests(
        self,
        argv: Sequence[str],
    ) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
        return self._call(Action.RUN_COMMANDS, 1, lambda: self.workspace.run_tests(argv))


class BuilderCapabilities(_CapabilityBase):
    """Typed branch, write, test, and commit capabilities for the Builder only."""

    def create_branch(self, name: str) -> tuple[None, tuple[dict[str, Any], ...]]:
        return self._call(Action.CREATE_BRANCH, 2, lambda: self.workspace.create_branch(name))

    def write_file(
        self,
        path: str,
        content: bytes,
    ) -> tuple[Path, tuple[dict[str, Any], ...]]:
        return self._call(
            Action.WRITE_WORKSPACE,
            0,
            lambda: self.workspace.write_file(path, content),
        )

    def run_tests(
        self,
        argv: Sequence[str],
    ) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
        return self._call(Action.RUN_COMMANDS, 1, lambda: self.workspace.run_tests(argv))

    def commit(self, message: str) -> tuple[str, tuple[dict[str, Any], ...]]:
        return self._call(
            Action.CREATE_BRANCH,
            3,
            lambda: self.workspace.commit(message),
        )


class CuratorCapabilities(_CapabilityBase):
    """Fresh delivery materialization, independent tests, and artifact verification."""

    def __init__(
        self,
        mission: RepositoryMission,
        workspace: GitWorkspace,
        candidate: Path,
    ) -> None:
        super().__init__(mission, Role.CURATOR, workspace)
        self.candidate = candidate

    def run_tests(
        self,
        argv: Sequence[str],
    ) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
        return self._call(Action.RUN_COMMANDS, 1, lambda: self.workspace.run_tests(argv))

    def verify_delivery(
        self,
    ) -> tuple[bool, tuple[dict[str, Any], ...]]:
        self._authorize(Action.READ_REPOSITORY)
        return self.mission._verify_candidate(self.candidate)


class ArchitectCapabilities:
    """Read-only design view; intentionally exposes no side-effect method."""

    def __init__(self, explorer_evidence: tuple[Evidence, ...]) -> None:
        self.explorer_evidence = explorer_evidence


class RepositoryMission:
    """Walk all eight roles from a local objective to a verified delivery artifact."""

    def __init__(
        self,
        repository: str | Path,
        objective: str,
        *,
        acceptance_criteria: Sequence[str] = (),
        backend: AgentBackend | None = None,
        pin: str | None = None,
        output_dir: str | Path = "hive-mind-delivery",
        policy: PolicyEngine | None = None,
        budget: AutonomyBudget | None = None,
        ledger: EvidenceLedger | None = None,
    ) -> None:
        self.repository = Path(repository).resolve()
        if not self.repository.is_dir() or not (self.repository / ".git").exists():
            raise ValueError("repository must be a local Git worktree")
        if not objective.strip():
            raise ValueError("objective is required")
        self.run_id = str(uuid4())
        self.objective = Objective(
            objective,
            id=self.run_id,
            repository=str(self.repository),
            acceptance_criteria=tuple(acceptance_criteria),
        )
        self.backend = backend or ScriptedRepositoryBackend()
        self.pin = pin
        self.output_dir = Path(os.path.abspath(output_dir))
        self.policy = policy or PolicyEngine(AutonomyLevel.REPOSITORY)
        self.budget = budget or AutonomyBudget(
            max_episodes=1000,
            max_tool_calls=500,
            max_compute_units=500.0,
            max_tool_calls_per_episode=100,
            max_compute_units_per_episode=100.0,
        )
        backend_budget = getattr(self.backend, "budget", None)
        if isinstance(backend_budget, AutonomyBudget):
            setattr(self.backend, "budget", self.budget)
        backend_ledger = getattr(self.backend, "ledger", None)
        if ledger is None and isinstance(backend_ledger, EvidenceLedger):
            self.ledger = backend_ledger
        else:
            self.ledger = ledger or EvidenceLedger()
            if isinstance(backend_ledger, EvidenceLedger):
                setattr(self.backend, "ledger", self.ledger)
        self._seen_receipts: set[tuple[str, str]] = set()
        self._receipt_records: list[dict[str, Any]] = []
        self._context_manifests: list[dict[str, Any]] = []
        self._evidence_root: Path | None = None

    async def run(self) -> MissionReport:
        started_at = utc_now()
        results: list[AgentResult] = []
        base_sha: str | None = None
        branch: str | None = None
        head_sha: str | None = None
        tree_digest: str | None = None
        artifact_directory: str | None = None
        receipt_root: str | None = None
        curator_verdict = "not-reached"
        builder_workspace_path: str | None = None
        curator_workspace_path: str | None = None
        failure: dict[str, str] | None = None
        staging_parent: Path | None = None
        published = False
        final_output = self._validated_output()
        explorer_test_argv: tuple[str, ...] | None = None
        self.ledger.append_event(
            self.run_id,
            "mission.started",
            Role.ORCHESTRATOR.value,
            {
                "objective_id": self.objective.id,
                "objective": self.objective.goal,
                "repository": str(self.repository),
                "output": str(final_output),
            },
        )

        try:
            if self.policy.autonomy < AutonomyLevel.REPOSITORY:
                self._authorize(Role.BUILDER, Action.WRITE_WORKSPACE)
            base_sha = self.pin or _read_local_head(self.repository)
            if not _is_full_sha(base_sha):
                raise MissionFailed("repository pin must be a full 40-hex SHA")

            output_parent = final_output.parent
            staging_parent = Path(
                tempfile.mkdtemp(
                    dir=output_parent,
                    prefix=f".{final_output.name}-mission-",
                )
            )
            candidate = staging_parent / "candidate"
            with tempfile.TemporaryDirectory(prefix="hive-mind-p05-") as temporary:
                work_root = Path(temporary)
                evidence_root = staging_parent / "evidence"
                evidence_root.mkdir()
                self._evidence_root = evidence_root
                explorer: ExplorerCapabilities | None = None
                builder_workspace: GitWorkspace | None = None
                curator_workspace: GitWorkspace | None = None
                builder_test_passed = False
                curator_test_passed = False
                criterion_passed = False
                delivery_verified = False

                for role in DEFAULT_LIFECYCLE:
                    self._authorize(role, Action.READ_REPOSITORY)
                    context = self._context_for(role, results)
                    manifest = self._context_manifest(role, context)
                    self._context_manifests.append(manifest)
                    self.ledger.append_event(
                        self.run_id,
                        "role.context",
                        role.value,
                        manifest,
                    )
                    work_item = WorkItem(
                        self.objective.id,
                        role,
                        self._instruction_for(role),
                        dependencies=tuple(item.work_item_id for item in context),
                    )
                    self.ledger.append_event(
                        self.run_id,
                        "role.started",
                        role.value,
                        asdict(work_item),
                    )
                    result = await self.backend.execute(
                        ROLE_CONTRACTS[role],
                        work_item,
                        self.objective,
                        context,
                    )
                    action_receipts: list[dict[str, Any]] = []

                    if role is Role.EXPLORER:
                        explorer_workspace = self._materialize(
                            base_sha,
                            work_root / "explorer",
                            Role.EXPLORER,
                        )
                        explorer = ExplorerCapabilities(
                            self,
                            Role.EXPLORER,
                            explorer_workspace,
                        )
                        for action in self._actions(result):
                            if action["action"] != "run_tests":
                                raise MissionFailed("Explorer proposed an unsupported action")
                            if explorer_test_argv is not None:
                                raise MissionFailed(
                                    "Explorer must propose exactly one test command"
                                )
                            explorer_test_argv = _string_argv(action.get("argv"))
                            receipt, records = explorer.run_tests(explorer_test_argv)
                            action_receipts.extend(records)
                            if receipt["result"] != "failed":
                                raise MissionFailed(
                                    "Explorer did not reproduce a failing repository test"
                                )
                        if explorer_test_argv is None:
                            raise MissionFailed(
                                "Explorer omitted the failure-reproducing test command"
                            )
                    elif role is Role.ARCHITECT:
                        ArchitectCapabilities(results[-1].evidence)
                        if result.proposed_actions:
                            raise MissionFailed(
                                "Architect received no side-effect capability"
                            )
                    elif role is Role.BUILDER:
                        builder_workspace = self._materialize(
                            base_sha,
                            work_root / "builder",
                            Role.BUILDER,
                        )
                        active_builder = builder_workspace
                        builder_workspace_path = str(active_builder.root)
                        builder = BuilderCapabilities(
                            self,
                            Role.BUILDER,
                            active_builder,
                        )
                        for action in self._actions(result):
                            name = action["action"]
                            if name == "create_branch":
                                _, records = builder.create_branch(_required_string(action, "name"))
                                action_receipts.extend(records)
                            elif name == "write_file":
                                try:
                                    content = base64.b64decode(
                                        _required_string(action, "content_base64"),
                                        validate=True,
                                    )
                                except ValueError:
                                    raise MissionFailed(
                                        "Builder content must be canonical base64"
                                    ) from None
                                _, records = builder.write_file(
                                    _required_string(action, "path"),
                                    content,
                                )
                                action_receipts.extend(records)
                            elif name == "run_tests":
                                test_argv = self._bound_test_argv(
                                    action,
                                    explorer_test_argv,
                                    Role.BUILDER,
                                )
                                receipt, records = builder.run_tests(
                                    test_argv
                                )
                                action_receipts.extend(records)
                                builder_test_passed = receipt["result"] == "succeeded"
                                if not builder_test_passed:
                                    raise MissionFailed("Builder test run failed")
                            elif name == "commit":
                                head_sha, records = builder.commit(
                                    _required_string(action, "message")
                                )
                                action_receipts.extend(records)
                            else:
                                raise MissionFailed("Builder proposed an unsupported action")
                        branch = active_builder.branch_name
                        if (
                            branch is None
                            or head_sha is None
                            or head_sha == base_sha
                            or not builder_test_passed
                        ):
                            raise MissionFailed(
                                "Builder omitted branch, tested change, or commit evidence"
                            )
                        tree_digest, tree_records = self._workspace_call(
                            active_builder,
                            1,
                            lambda: active_builder._git_text(
                                ["rev-parse", "HEAD^{tree}"],
                                Action.READ_REPOSITORY,
                                "read mission delivery tree",
                            ),
                        )
                        action_receipts.extend(tree_records)
                        self._authorize(Role.BUILDER, Action.WRITE_WORKSPACE)
                        _, export_records = self._workspace_call(
                            active_builder,
                            7,
                            lambda: active_builder.export_delivery(candidate),
                        )
                        action_receipts.extend(export_records)
                    elif role is Role.CURATOR:
                        if builder_workspace is None or not candidate.is_dir():
                            raise MissionFailed("Curator lacks a candidate delivery")
                        curator_workspace = self._materialize_delivery(
                            base_sha,
                            candidate,
                            work_root / "curator",
                        )
                        curator_workspace_path = str(curator_workspace.root)
                        curator = CuratorCapabilities(
                            self,
                            curator_workspace,
                            candidate,
                        )
                        for action in self._actions(result):
                            name = action["action"]
                            if name == "run_tests":
                                test_argv = self._bound_test_argv(
                                    action,
                                    explorer_test_argv,
                                    Role.CURATOR,
                                )
                                receipt, records = curator.run_tests(
                                    test_argv
                                )
                                action_receipts.extend(records)
                                passed = receipt["result"] == "succeeded"
                                curator_test_passed = passed
                            elif name == "run_criterion":
                                receipt, records = curator.run_tests(
                                    _string_argv(action.get("argv"))
                                )
                                action_receipts.extend(records)
                                criterion_passed = receipt["result"] == "succeeded"
                            elif name == "verify_delivery":
                                delivery_verified, records = curator.verify_delivery()
                                action_receipts.extend(records)
                            else:
                                raise MissionFailed("Curator proposed an unsupported action")
                        curator_verdict = (
                            "adopt"
                            if curator_test_passed
                            and criterion_passed
                            and delivery_verified
                            else "reject"
                        )
                        self.ledger.append_event(
                            self.run_id,
                            "curator.verdict",
                            Role.CURATOR.value,
                            {
                                "verdict": curator_verdict,
                                "tests_passed": curator_test_passed,
                                "criterion_passed": criterion_passed,
                                "delivery_verified": delivery_verified,
                                "workspace": curator_workspace_path,
                            },
                        )
                        if curator_verdict != "adopt":
                            self.ledger.append_event(
                                self.run_id,
                                "curator.divergence",
                                Role.CURATOR.value,
                                {
                                    "builder_tests_passed": builder_test_passed,
                                    "curator_tests_passed": curator_test_passed,
                                    "criterion_passed": criterion_passed,
                                },
                            )
                            raise MissionFailed(
                                "Curator rejected the Builder candidate"
                            )
                    elif result.proposed_actions:
                        raise MissionFailed(
                            f"{role.value} received no side-effect capability"
                        )

                    result = self._with_receipt_evidence(result, action_receipts)
                    HiveKernel._validate_result(role, result)
                    results.append(result)
                    self.ledger.append_event(
                        self.run_id,
                        "role.completed",
                        role.value,
                        HiveKernel._result_payload(result),
                    )
                    self.ledger.append_lessons(
                        self.run_id,
                        role.value,
                        result.lessons,
                    )

                if (
                    builder_workspace is None
                    or curator_workspace is None
                    or curator_verdict != "adopt"
                    or head_sha is None
                    or tree_digest is None
                ):
                    raise MissionFailed("mission reached an incomplete delivery state")
                self._copy_and_validate_mission_evidence(candidate)
                os.replace(candidate, final_output)
                published = True
                artifact_directory = str(final_output)
                receipt_root = str(final_output / "mission-evidence")
                self.ledger.append_event(
                    self.run_id,
                    "artifact.exported",
                    Role.INTEGRATOR.value,
                    {
                        "artifact_directory": artifact_directory,
                        "base_sha": base_sha,
                        "head_sha": head_sha,
                        "tree_digest": tree_digest,
                    },
                )

            self.ledger.append_event(
                self.run_id,
                "mission.completed",
                Role.ORCHESTRATOR.value,
                {
                    "objective_id": self.objective.id,
                    "result_count": len(results),
                    "curator_verdict": curator_verdict,
                },
            )
            report = self._report(
                results,
                WorkStatus.SUCCEEDED,
                started_at,
                base_sha,
                branch,
                head_sha,
                tree_digest,
                artifact_directory,
                receipt_root,
                curator_verdict,
                builder_workspace_path,
                curator_workspace_path,
                None,
            )
            assert artifact_directory is not None
            (Path(artifact_directory) / "mission-report.json").write_text(
                json.dumps(
                    report.to_dict(),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            return report
        except Exception as error:
            failure = {
                "type": type(error).__name__,
                "message": str(error),
            }
            if isinstance(error, BudgetExceeded) or "allowance" in str(error).lower():
                self.ledger.append_event(
                    self.run_id,
                    "budget.exhausted",
                    Role.ORCHESTRATOR.value,
                    failure,
                )
            self.ledger.append_event(
                self.run_id,
                "mission.failed",
                Role.ORCHESTRATOR.value,
                failure,
            )
            if published and final_output.exists():
                shutil.rmtree(final_output)
            failure_receipt_root = self._preserve_failure_evidence(final_output)
            report = self._report(
                results,
                WorkStatus.FAILED,
                started_at,
                base_sha,
                branch,
                head_sha,
                tree_digest,
                None,
                failure_receipt_root,
                curator_verdict,
                builder_workspace_path,
                curator_workspace_path,
                failure,
            )
            if failure_receipt_root is not None:
                (Path(failure_receipt_root) / "mission-report.json").write_text(
                    json.dumps(
                        report.to_dict(),
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
            return report
        finally:
            if staging_parent is not None and staging_parent.exists():
                shutil.rmtree(staging_parent)

    def _validated_output(self) -> Path:
        parent = self.output_dir.parent
        if not parent.is_dir():
            raise ValueError("output parent must be an existing directory")
        if parent.resolve() != parent:
            raise ValueError("output parent must not traverse a symlink or junction")
        if self.output_dir.exists() or self.output_dir.is_symlink():
            raise ValueError("output directory must not already exist")
        try:
            self.output_dir.relative_to(self.repository)
        except ValueError:
            return self.output_dir
        raise ValueError("output directory must be outside the source repository")

    def _authorize(self, role: Role, action: Action) -> None:
        decision = self.policy.decide(role, action, self.objective.risk)
        self.ledger.append_event(
            self.run_id,
            "policy.decision",
            role.value,
            {
                "action": action.value,
                "allowed": decision.allowed,
                "reason": decision.reason,
                "autonomy_level": int(self.policy.autonomy),
            },
        )
        if not decision.allowed:
            raise GitPolicyDenied(decision.reason)

    def _reserve(self, expected_calls: int) -> EpisodeAllowance:
        allowance = self.budget.issue_allowance()
        if (
            allowance.tool_calls < expected_calls
            or allowance.compute_units < float(expected_calls)
        ):
            raise BudgetExceeded(
                f"mission allowance exhausted before {expected_calls} tool calls"
            )
        return allowance

    def _consume(self, allowance: EpisodeAllowance, tool_calls: int) -> None:
        self.budget.consume(
            allowance,
            tool_calls=tool_calls,
            compute_units=float(tool_calls),
        )
        self.ledger.append_event(
            self.run_id,
            "budget.consumed",
            Role.ORCHESTRATOR.value,
            {
                "tool_calls": tool_calls,
                "compute_units": float(tool_calls),
                "episodes_used": self.budget.episodes_used,
            },
        )

    def _materialize(
        self,
        base_sha: str,
        root: Path,
        role: Role,
    ) -> GitWorkspace:
        self._authorize(role, Action.READ_REPOSITORY)
        allowance = self._reserve(3)
        assert self._evidence_root is not None
        before = set((self._evidence_root / "receipts").glob("*.json"))
        try:
            workspace = GitWorkspace.materialize(
                self.repository,
                base_sha,
                root,
                self._evidence_root,
                policy=self.policy,
                role=role,
                allowance=allowance,
            )
        finally:
            after = set((self._evidence_root / "receipts").glob("*.json"))
            used = len(after - before)
            self._consume(allowance, used)
        self._record_workspace_receipts(workspace)
        self.ledger.append_event(
            self.run_id,
            "workspace.materialized",
            role.value,
            {
                "workspace": str(workspace.root),
                "base_sha": base_sha,
                "fresh": True,
            },
        )
        return workspace

    def _materialize_delivery(
        self,
        base_sha: str,
        candidate: Path,
        root: Path,
    ) -> GitWorkspace:
        workspace = self._materialize(base_sha, root, Role.CURATOR)
        bundle = (candidate / "changes.bundle").read_bytes()
        self._authorize(Role.CURATOR, Action.WRITE_WORKSPACE)
        self._workspace_call(
            workspace,
            0,
            lambda: workspace.write_file("candidate.bundle", bundle),
        )
        manifest = json.loads(
            (candidate / "delivery.json").read_text(encoding="utf-8")
        )
        branch = _required_string(manifest, "branch_name")
        head_sha = _required_string(manifest, "head_sha")
        self._authorize(Role.CURATOR, Action.READ_REPOSITORY)
        self._workspace_call(
            workspace,
            2,
            lambda: (
                workspace._run_git(
                    [
                        "fetch",
                        "candidate.bundle",
                        f"{branch}:refs/heads/{branch}",
                    ],
                    Action.READ_REPOSITORY,
                    "materialize candidate bundle for Curator",
                    path_args=[1],
                ),
                workspace._run_git(
                    ["checkout", "--detach", head_sha],
                    Action.READ_REPOSITORY,
                    "checkout candidate head for Curator",
                ),
            ),
        )
        self.ledger.append_event(
            self.run_id,
            "curator.workspace.materialized",
            Role.CURATOR.value,
            {
                "workspace": str(workspace.root),
                "source": "candidate bundle",
                "head_sha": head_sha,
            },
        )
        return workspace

    def _workspace_call(
        self,
        workspace: GitWorkspace,
        expected_calls: int,
        operation: Callable[[], _T],
    ) -> tuple[_T, tuple[dict[str, Any], ...]]:
        allowance = self._reserve(expected_calls)
        before = len(workspace.receipt_records)
        try:
            value = operation()
        except Exception as operation_error:
            records = tuple(
                dict(record) for record in workspace.receipt_records[before:]
            )
            accounting_errors: list[str] = []
            try:
                self._consume(allowance, len(records))
            except Exception as accounting_error:
                accounting_errors.append(
                    f"budget accounting failed: {type(accounting_error).__name__}: "
                    f"{accounting_error}"
                )
            try:
                self._record_workspace_receipts(workspace)
            except Exception as accounting_error:
                accounting_errors.append(
                    f"receipt recording failed: {type(accounting_error).__name__}: "
                    f"{accounting_error}"
                )
            if accounting_errors:
                operation_error.add_note("; ".join(accounting_errors))
            raise
        records = tuple(
            dict(record) for record in workspace.receipt_records[before:]
        )
        self._consume(allowance, len(records))
        self._record_workspace_receipts(workspace)
        return value, records

    def _preserve_failure_evidence(self, final_output: Path) -> str | None:
        if not self._receipt_records:
            return None
        if self._evidence_root is None or not self._evidence_root.is_dir():
            raise MissionFailed("failed-run receipt evidence is unavailable")
        destination = final_output.with_name(
            f".{final_output.name}-failed-evidence-{self.run_id}"
        )
        if destination.exists() or destination.is_symlink():
            raise MissionFailed("failed-run evidence destination already exists")
        os.replace(self._evidence_root, destination)
        validator = FileReceiptValidator(destination)
        for record in self._receipt_records:
            validation = validator.validate(
                ReceiptReference(
                    str(record["path"]),
                    str(record["digest"]),
                ),
                mission_id=str(record["mission_id"]),
                state_ref=str(record["state_ref"]),
                actor_id=str(record["actor_id"]),
                action_id=str(record["action_id"]),
                action_kind=str(record["action_kind"]),
                action_digest=str(record["action_digest"]),
            )
            if not validation.valid:
                raise MissionFailed(
                    "failed-run receipt failed validation: "
                    + "; ".join(validation.issues)
                )
        return str(destination)

    def _verify_candidate(
        self,
        candidate: Path,
    ) -> tuple[bool, tuple[dict[str, Any], ...]]:
        allowance = self._reserve(17)
        records: list[dict[str, Any]] = []
        assert self._evidence_root is not None
        try:
            verified = verify_delivery(
                candidate,
                self.repository,
                evidence_root=self._evidence_root,
                receipt_records=records,
                policy=self.policy,
                role=Role.CURATOR,
                allowance=allowance,
            )
        finally:
            self._consume(allowance, len(records))
            self._record_receipts(records)
        return verified, tuple(dict(record) for record in records)

    def _record_workspace_receipts(self, workspace: GitWorkspace) -> None:
        self._record_receipts(workspace.receipt_records)

    def _record_receipts(
        self,
        records: Sequence[Mapping[str, Any]],
    ) -> None:
        for record in records:
            key = (str(record["path"]), str(record["digest"]))
            if key in self._seen_receipts:
                continue
            copied = dict(record)
            self._seen_receipts.add(key)
            self._receipt_records.append(copied)
            self.ledger.append_event(
                self.run_id,
                "receipt.recorded",
                str(record["actor_id"]),
                copied,
            )

    def _copy_and_validate_mission_evidence(self, candidate: Path) -> None:
        assert self._evidence_root is not None
        destination = candidate / "mission-evidence"
        shutil.copytree(self._evidence_root, destination)
        validator = FileReceiptValidator(destination)
        for record in self._receipt_records:
            validation = validator.validate(
                ReceiptReference(
                    str(record["path"]),
                    str(record["digest"]),
                ),
                mission_id=str(record["mission_id"]),
                state_ref=str(record["state_ref"]),
                actor_id=str(record["actor_id"]),
                action_id=str(record["action_id"]),
                action_kind=str(record["action_kind"]),
                action_digest=str(record["action_digest"]),
            )
            if not validation.valid:
                raise MissionFailed(
                    "mission receipt failed validation: "
                    + "; ".join(validation.issues)
                )

    @staticmethod
    def _actions(result: AgentResult) -> tuple[dict[str, Any], ...]:
        actions: list[dict[str, Any]] = []
        for raw in result.proposed_actions:
            try:
                action = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                raise MissionFailed(
                    "proposed actions must be JSON objects encoded as strings"
                ) from None
            if not isinstance(action, dict) or not isinstance(
                action.get("action"), str
            ):
                raise MissionFailed("proposed action lacks a typed action name")
            actions.append(action)
        return tuple(actions)

    @staticmethod
    def _bound_test_argv(
        action: Mapping[str, Any],
        explorer_test_argv: tuple[str, ...] | None,
        role: Role,
    ) -> tuple[str, ...]:
        if explorer_test_argv is None:
            raise MissionFailed("failure-reproducing test command is not sealed")
        proposed = _string_argv(action.get("argv"))
        if proposed != explorer_test_argv:
            raise MissionFailed(
                f"{role.value} test command differs from the "
                "Explorer failure-reproducing command"
            )
        return explorer_test_argv

    @staticmethod
    def _with_receipt_evidence(
        result: AgentResult,
        records: Sequence[Mapping[str, Any]],
    ) -> AgentResult:
        if not records:
            return result
        digests = [str(record["digest"]) for record in records]
        enriched = tuple(
            replace(
                evidence,
                payload={
                    **evidence.payload,
                    "receipt_digests": digests,
                },
            )
            for evidence in result.evidence
        )
        return replace(
            result,
            evidence=(
                *enriched,
                Evidence(
                    kind="capability-receipts",
                    summary="role side effects are bound to enforcement receipts",
                    source=f"mission:{result.role.value}",
                    payload={"receipt_digests": digests},
                ),
            ),
        )

    @staticmethod
    def _context_for(
        role: Role,
        results: Sequence[AgentResult],
    ) -> tuple[AgentResult, ...]:
        if role is Role.CURATOR:
            return tuple(item for item in results if item.role is not Role.BUILDER)
        return tuple(results)

    @staticmethod
    def _context_manifest(
        role: Role,
        context: Sequence[AgentResult],
    ) -> dict[str, Any]:
        return {
            "role": role.value,
            "prior_roles": [item.role.value for item in context],
            "summaries": [item.summary for item in context],
            "receipt_digests": [
                digest
                for item in context
                for evidence in item.evidence
                for digest in evidence.payload.get("receipt_digests", [])
                if isinstance(digest, str)
            ],
        }

    @staticmethod
    def _instruction_for(role: Role) -> str:
        action_guidance = {
            Role.EXPLORER: (
                "Use only a JSON-string proposed action named run_tests with argv."
            ),
            Role.BUILDER: (
                "Use JSON-string proposed actions create_branch, write_file "
                "(portable path plus base64 content), run_tests, and commit."
            ),
            Role.CURATOR: (
                "Use only JSON-string proposed actions run_tests, run_criterion, "
                "and verify_delivery. Builder rationale and receipts are withheld."
            ),
        }
        return (
            ROLE_CONTRACTS[role].mission
            + " "
            + action_guidance.get(
                role,
                "No side-effect capability is available; proposed_actions must be empty.",
            )
        )

    def _report(
        self,
        results: Sequence[AgentResult],
        status: WorkStatus,
        started_at: str,
        base_sha: str | None,
        branch: str | None,
        head_sha: str | None,
        tree_digest: str | None,
        artifact_directory: str | None,
        receipt_root: str | None,
        curator_verdict: str,
        builder_workspace: str | None,
        curator_workspace: str | None,
        failure: dict[str, str] | None,
    ) -> MissionReport:
        events = self.ledger.events(self.run_id)
        return MissionReport(
            run_id=self.run_id,
            objective_id=self.objective.id,
            results=tuple(results),
            status=status,
            started_at=started_at,
            completed_at=utc_now(),
            objective=self.objective.goal,
            repository=str(self.repository),
            base_sha=base_sha,
            branch=branch,
            head_sha=head_sha,
            tree_digest=tree_digest,
            artifact_directory=artifact_directory,
            receipt_root=receipt_root,
            receipts=tuple(dict(record) for record in self._receipt_records),
            curator_verdict=curator_verdict,
            budget_consumption={
                "episodes": self.budget.episodes_used,
                "tool_calls": self.budget.tool_calls_used,
                "compute_units": self.budget.compute_units_used,
            },
            event_types=tuple(event["event_type"] for event in events),
            ledger_events=tuple(dict(event) for event in events),
            builder_workspace=builder_workspace,
            curator_workspace=curator_workspace,
            context_manifests=tuple(dict(item) for item in self._context_manifests),
            failure=failure,
        )


def _required_string(document: Mapping[str, Any], field: str) -> str:
    value = document.get(field)
    if not isinstance(value, str) or not value.strip():
        raise MissionFailed(f"{field} must be a nonempty string")
    return value


def _string_argv(value: object) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item for item in value)
    ):
        raise MissionFailed("argv must be a nonempty string list")
    return tuple(value)


def _is_full_sha(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(character in "0123456789abcdefABCDEF" for character in value)
    )


def _read_local_head(repository: Path) -> str:
    """Resolve a local worktree HEAD without invoking an ambient Git subprocess."""

    git_marker = repository / ".git"
    if git_marker.is_file():
        marker = git_marker.read_text(encoding="utf-8").strip()
        if not marker.startswith("gitdir: "):
            raise MissionFailed("worktree .git file is malformed")
        git_dir = (repository / marker.removeprefix("gitdir: ")).resolve()
    else:
        git_dir = git_marker.resolve()
    head = (git_dir / "HEAD").read_text(encoding="ascii").strip()
    if _is_full_sha(head):
        return head.lower()
    if not head.startswith("ref: "):
        raise MissionFailed("repository HEAD is neither a full SHA nor symbolic ref")
    reference = head.removeprefix("ref: ")
    if "\\" in reference or ".." in reference.split("/"):
        raise MissionFailed("repository HEAD ref is nonportable")
    loose = git_dir.joinpath(*reference.split("/"))
    if loose.is_file():
        value = loose.read_text(encoding="ascii").strip()
        if _is_full_sha(value):
            return value.lower()
    packed = git_dir / "packed-refs"
    if packed.is_file():
        for line in packed.read_text(encoding="ascii").splitlines():
            if not line or line.startswith(("#", "^")):
                continue
            value, _, name = line.partition(" ")
            if name == reference and _is_full_sha(value):
                return value.lower()
    raise MissionFailed("repository HEAD ref does not resolve to a full local SHA")
