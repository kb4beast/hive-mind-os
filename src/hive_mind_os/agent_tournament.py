"""Repository-wide, evidence-bearing tournament for the eight Hive Mind agents.

The tournament is deliberately additive.  It does not promote a prompt, mutate an
agent, authorize an external effect, or claim that a passing synthetic check proves
customer value.  It executes a bounded dependency DAG, grades every role on its own
evidence, grades their composition, preserves adverse evidence, and emits explicit
feedback/re-entry contracts for the next challenger generation.
"""

from __future__ import annotations

import argparse
import ast
import base64
import binascii
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .brain_kernel.canonical import canonical_digest
from .brain_kernel.roles import KERNEL_IMPLEMENTED_ROLES, role_capabilities
from .models import Role
from .roles import ROLE_CONTRACTS

TOURNAMENT_ROLES: tuple[str, ...] = (
    "orchestrator",
    "explorer",
    "architect",
    "builder",
    "curator",
    "integrator",
    "steward",
    "optimizer",
)
DISPOSITIONS = frozenset({"adopt", "adapt", "defer", "reject", "quarantine"})
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_UNITTEST_SUMMARY = re.compile(r"(?m)^Ran (\d+) tests? in [^\r\n]+\r?$")
_UNITTEST_VERDICT = re.compile(r"(?m)^(OK|FAILED)(?: \(([^\r\n]+)\))?\r?$")
_SKIP_COUNT = re.compile(r"(?:^|, )skipped=(\d+)(?:,|$)")
_LIMITED_REPOSITORY_ROLES = frozenset({"explorer", "builder", "curator"})
_GIT_TIMEOUT_SECONDS = 120
_PROVENANCE_TIMEOUT_SECONDS = 30
_MAX_GIT_STREAM_BYTES = 64 * 1024 * 1024
_MAX_COMMAND_STREAM_BYTES = 16 * 1024 * 1024
_MAX_INVENTORY_FILE_BYTES = 256 * 1024 * 1024
_MAX_INVENTORY_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
_MAX_RUN_ARTIFACT_BYTES = 64 * 1024 * 1024
_MAX_RUN_TOTAL_BYTES = 1024 * 1024 * 1024
_CANONICAL_SCORING_POLICY = {
    "development_scores_are_advisory": True,
    "fatal_gates_are_non_compensating": True,
    "imperfect_champions_route_to_adapt_not_elimination": True,
    "allowed_dispositions": sorted(DISPOSITIONS),
}
_CANONICAL_FEEDBACK_POLICY = {
    "champions_are_immutable_during_generation": True,
    "max_cycles": 3,
    "restart_from": "SCAN-REPOSITORY",
    "promotion_requires_separate_independent_court": True,
}
_CANONICAL_RETRY_POLICY = {
    "retry_only_infrastructure_exceptions": True,
    "record_every_wave_result_before_abort": True,
    "write_terminal_manifest_on_exhaustion": True,
}
_CANONICAL_EXECUTOR = {
    "module": "hive_mind_os.agent_tournament",
    "command": (
        "python -B scripts/run_agent_tournament.py run --repository . "
        "--output-dir <new-directory>"
    ),
}
_CHILD_OPTIONAL_ENV_NAMES = frozenset(
    {
        "COMSPEC",
        "LANG",
        "LC_ALL",
        "NUMBER_OF_PROCESSORS",
        "PROCESSOR_ARCHITECTURE",
        "SYSTEMDRIVE",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "WINDIR",
    }
)
_CHILD_REQUIRED_ENV_NAMES = frozenset(
    {
        "ALL_PROXY",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "PATH",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONHASHSEED",
        "PYTHONNOUSERSITE",
        "PYTHONPATH",
        "PYTHONSAFEPATH",
        "PYTHONUTF8",
    }
)


class TournamentError(RuntimeError):
    """The tournament cannot produce trustworthy evidence."""


@dataclass(frozen=True, slots=True)
class RoleAuditSpec:
    implementation_module: str
    implementation_symbol: str
    test_modules: tuple[str, ...]
    purpose: str


ROLE_AUDIT_SPECS: Mapping[str, RoleAuditSpec] = {
    "orchestrator": RoleAuditSpec(
        "hive_mind_os.brain_kernel.planner",
        "OrchestratorPlanner",
        ("tests.test_hive_cortex_orchestrator", "tests.test_brain_kernel_planner"),
        "decompose objectives, budget work, and stop safely",
    ),
    "explorer": RoleAuditSpec(
        "hive_mind_os.brain_kernel.explorer",
        "RepositoryExplorer",
        ("tests.test_hive_cortex_explorer",),
        "inspect repository evidence without mutating it",
    ),
    "architect": RoleAuditSpec(
        "hive_mind_os.brain_kernel.architect",
        "Architect",
        ("tests.test_hive_cortex_architect",),
        "produce interfaces, threats, migration, and rollback",
    ),
    "builder": RoleAuditSpec(
        "hive_mind_os.brain_kernel.builder",
        "BuilderCoordinator",
        ("tests.test_hive_cortex_builder",),
        "create bounded code and test changes through typed effects",
    ),
    "curator": RoleAuditSpec(
        "hive_mind_os.brain_kernel.curator_runtime",
        "CuratorRuntime",
        ("tests.test_hive_cortex_curator",),
        "independently verify the exact candidate without mutation",
    ),
    "integrator": RoleAuditSpec(
        "hive_mind_os.brain_kernel.integrator",
        "Integrator",
        ("tests.test_hive_cortex_integrator",),
        "compose versioned contracts and remand repairs to Builder",
    ),
    "steward": RoleAuditSpec(
        "hive_mind_os.brain_kernel.steward",
        "Steward",
        ("tests.test_hive_cortex_steward",),
        "assess health, recovery, and operational readiness",
    ),
    "optimizer": RoleAuditSpec(
        "hive_mind_os.brain_kernel.optimizer",
        "Optimizer",
        ("tests.test_hive_cortex_optimizer",),
        "attribute outcomes and propose immutable challengers",
    ),
}


SYSTEM_TEST_LANES: Mapping[str, tuple[str, ...]] = {
    "lifecycle": (
        "tests.test_hive_cortex_role_runtime",
        "tests.test_hive_cortex_mission_runtime",
        "tests.test_brain_kernel_roles",
    ),
    "code-qa": ("tests.test_verify_example", "tests.test_mission"),
    "resilience": (
        "tests.test_hive_cortex_self_healing",
        "tests.test_hive_cortex_durability",
        "tests.hive_cortex.test_no_cheating",
        "tests.hive_cortex.test_learning_poisoning",
    ),
    "evolution": (
        "tests.test_hive_cortex_challengers",
        "tests.test_hive_cortex_evaluation",
        "tests.test_hive_cortex_learning",
        "tests.test_hive_cortex_promotion",
        "tests.test_recursive_improvement",
    ),
}


def _required_inventory_paths() -> frozenset[str]:
    paths = {
        "pyproject.toml",
        "scripts/run_agent_tournament.py",
        "src/hive_mind_os/agent_tournament.py",
        "src/hive_mind_os/cli.py",
        "src/hive_mind_os/roles.py",
        "tests/test_agent_tournament.py",
    }
    for role in TOURNAMENT_ROLES:
        paths.update(
            {
                f"src/hive_mind_os/builtin_packages/hive-core/agents/{role}.json",
                f"src/hive_mind_os/builtin_packages/hive-core/prompts/{role}.json",
                f"src/hive_mind_os/builtin_packages/hive-core/skills/{role}.json",
                f"src/hive_mind_os/builtin_packages/hive-core/skills/instructions/{role}.json",
            }
        )
    return frozenset(paths)


@dataclass(frozen=True, slots=True)
class DagNode:
    node_id: str
    action: str
    dependencies: tuple[str, ...]
    parallel_safe: bool
    objective: str
    role: str | None = None
    lane: str | None = None
    read_scope: tuple[str, ...] = ()
    write_scope: tuple[str, ...] = ()
    acceptance: tuple[str, ...] = ()
    hard_gates: tuple[str, ...] = ()
    max_attempts: int = 1

    def document(self) -> dict[str, Any]:
        return asdict(self)


def _role_node_id(role: str) -> str:
    return "ROLE-" + role.upper()


def _feedback_node_id(role: str) -> str:
    return "FEEDBACK-" + role.upper()


def _canonical_plan_document() -> dict[str, Any]:
    """Build the code-owned canonical tournament document without recursion."""

    nodes: list[DagNode] = [
        DagNode(
            "SCAN-REPOSITORY",
            "inventory",
            (),
            False,
            "Hash and classify every versioned or unignored repository file.",
            read_scope=("**",),
            write_scope=("run://receipts/SCAN-REPOSITORY.json",),
            acceptance=("every discovered file has a path, size, and content digest",),
            hard_gates=("repository root and source package are present",),
        )
    ]
    for role in TOURNAMENT_ROLES:
        nodes.append(
            DagNode(
                _role_node_id(role),
                "grade-role",
                ("SCAN-REPOSITORY",),
                True,
                f"Grade the {role} separately against its own declared purpose.",
                role=role,
                read_scope=("**",),
                write_scope=(
                    f"run://receipts/{_role_node_id(role)}.json",
                    f"run://transcripts/{_role_node_id(role)}.txt",
                ),
                acceptance=(
                    "identity and artifacts validate",
                    "module-scope specialized implementation declaration is present",
                    "role-focused tests execute and pass",
                    "weaknesses remain visible even when the score passes",
                ),
                hard_gates=("role identity is registered", "evidence is not fabricated"),
                max_attempts=2,
            )
        )

    role_dependencies = tuple(_role_node_id(role) for role in TOURNAMENT_ROLES)
    for lane in ("static", *SYSTEM_TEST_LANES, "control-plane"):
        action = {
            "static": "static-repository",
            "control-plane": "control-plane-audit",
        }.get(lane, "system-test")
        nodes.append(
            DagNode(
                "SYSTEM-" + lane.upper(),
                action,
                role_dependencies,
                True,
                {
                    "static": "Parse every discovered Python and JSON artifact.",
                    "lifecycle": "Prove all roles compose in the canonical lifecycle.",
                    "code-qa": (
                        "Exercise the existing code-to-QA bridge fixtures; this run does not "
                        "author a novel change."
                    ),
                    "resilience": "Exercise recovery, no-cheating, and learning-poisoning defenses.",
                    "evolution": "Exercise challenger, evaluation, learning, and promotion boundaries.",
                    "control-plane": "Cross-check the installed legacy control plane under strict lint.",
                }[lane],
                lane=lane,
                read_scope=("**",),
                write_scope=(
                    f"run://receipts/SYSTEM-{lane.upper()}.json",
                    *(
                        ()
                        if lane == "static"
                        else (f"run://transcripts/SYSTEM-{lane.upper()}.txt",)
                    ),
                ),
                acceptance=("lane produces a reproducible receipt",),
                hard_gates=("a catastrophic defect is not averaged away",),
            )
        )

    component_nodes = tuple(
        "SYSTEM-" + lane.upper() for lane in ("static", *SYSTEM_TEST_LANES, "control-plane")
    )
    nodes.extend(
        (
            DagNode(
                "SYSTEM-FULL-SUITE",
                "full-suite",
                component_nodes,
                False,
                "Run the repository's complete CI test gate from this checkout.",
                lane="full-suite",
                read_scope=("**",),
                write_scope=(
                    "run://receipts/SYSTEM-FULL-SUITE.json",
                    "run://transcripts/SYSTEM-FULL-SUITE.txt",
                ),
                acceptance=("the canonical full suite is executed or explicitly deferred",),
                hard_gates=("failed tests are retained",),
            ),
            DagNode(
                "CROSS-EXAMINE",
                "cross-examine",
                ("SYSTEM-FULL-SUITE",),
                False,
                "Attack every apparent pass and expose gaps hidden by aggregate scores.",
                read_scope=("run://receipts/**", "**"),
                write_scope=("run://receipts/CROSS-EXAMINE.json",),
                acceptance=("fatal findings and development gaps are classified separately",),
                hard_gates=("the cross-examiner cannot erase or promote evidence",),
            ),
        )
    )
    for role in TOURNAMENT_ROLES:
        nodes.append(
            DagNode(
                _feedback_node_id(role),
                "feedback",
                (_role_node_id(role), "CROSS-EXAMINE"),
                True,
                f"Execute bounded challenge synthesis for {role} and define a fresh-run re-entry path.",
                role=role,
                read_scope=(
                    f"run://receipts/{_role_node_id(role)}.json",
                    "run://receipts/CROSS-EXAMINE.json",
                ),
                write_scope=(f"run://receipts/{_feedback_node_id(role)}.json",),
                acceptance=(
                    "the live champion is not mutated",
                    "challenge hypotheses cite observed evidence",
                    "three challenge stages execute before a fresh-run re-entry contract is emitted",
                ),
                hard_gates=("feedback cannot promote itself",),
                max_attempts=3,
            )
        )
    nodes.append(
        DagNode(
            "CHAMPIONSHIP",
            "championship",
            tuple(_feedback_node_id(role) for role in TOURNAMENT_ROLES),
            False,
            "Judge separately derived role readiness and whole-system readiness together.",
            read_scope=("run://**",),
            write_scope=(
                "run://receipts/CHAMPIONSHIP.json",
                "run://report.json",
                "run://report.md",
            ),
            acceptance=(
                "all eight separately derived grades are present",
                "whole-system gates are present",
                "dissent, losing evidence, and feedback routes are retained",
            ),
            hard_gates=(
                "declared judge and affected-champion identities do not overlap",
                "actual independent execution remains mandatory before promotion",
                "no score hides a fatal defect",
            ),
        )
    )
    document: dict[str, Any] = {
        "schema_version": 1,
        "kind": "hive-mind-agent-readiness-tournament-dag",
        "plan_id": "agent-readiness-tournament-v1",
        "objective": (
            "Grade every constitutional agent separately and in composition, exercise the existing "
            "code-to-QA bridge fixtures, and route weaknesses into bounded immutable challenger "
            "re-entry contracts."
        ),
        "max_parallelism": len(TOURNAMENT_ROLES),
        "source_of_truth": "live checkout plus immutable run receipts",
        "scoring_policy": dict(_CANONICAL_SCORING_POLICY),
        "feedback_policy": dict(_CANONICAL_FEEDBACK_POLICY),
        "retry_policy": dict(_CANONICAL_RETRY_POLICY),
        "executor": dict(_CANONICAL_EXECUTOR),
        "nodes": [node.document() for node in nodes],
    }
    document["plan_digest"] = canonical_digest(document)
    return document


def build_tournament_plan() -> dict[str, Any]:
    """Build the immutable, provider-neutral executable tournament DAG."""

    document = _canonical_plan_document()
    validate_tournament_plan(document)
    return document


def validate_tournament_plan(document: Mapping[str, Any]) -> tuple[tuple[str, ...], ...]:
    """Validate the graph and return deterministic, conflict-free execution waves."""

    expected_plan_fields = {
        "schema_version",
        "kind",
        "plan_id",
        "objective",
        "max_parallelism",
        "source_of_truth",
        "scoring_policy",
        "feedback_policy",
        "retry_policy",
        "executor",
        "nodes",
        "plan_digest",
    }
    if set(document) != expected_plan_fields:
        raise TournamentError("tournament plan fields are invalid")
    if type(document.get("schema_version")) is not int or document["schema_version"] != 1:
        raise TournamentError("tournament plan schema is invalid")
    if document.get("kind") != "hive-mind-agent-readiness-tournament-dag":
        raise TournamentError("tournament plan kind is invalid")
    supplied_digest = document.get("plan_digest")
    material = dict(document)
    material.pop("plan_digest", None)
    if supplied_digest != canonical_digest(material):
        raise TournamentError("tournament plan digest does not bind the plan")
    raw_nodes = document.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise TournamentError("tournament plan requires nodes")
    if document.get("executor") != _CANONICAL_EXECUTOR:
        raise TournamentError("tournament plan lacks the canonical executable entry point")
    if document.get("scoring_policy") != _CANONICAL_SCORING_POLICY:
        raise TournamentError("tournament scoring policy was weakened or is incomplete")
    if document.get("feedback_policy") != _CANONICAL_FEEDBACK_POLICY:
        raise TournamentError("tournament feedback policy was weakened or is incomplete")
    if document.get("retry_policy") != _CANONICAL_RETRY_POLICY:
        raise TournamentError("tournament retry policy was weakened or is incomplete")
    limit = document.get("max_parallelism")
    if type(limit) is not int or limit != len(TOURNAMENT_ROLES):
        raise TournamentError("max_parallelism must preserve the canonical eight-role wave")
    by_id: dict[str, Mapping[str, Any]] = {}
    allowed_actions = {
        "inventory",
        "grade-role",
        "static-repository",
        "system-test",
        "control-plane-audit",
        "full-suite",
        "cross-examine",
        "feedback",
        "championship",
    }
    for raw in raw_nodes:
        if not isinstance(raw, Mapping):
            raise TournamentError("tournament node must be an object")
        if set(raw) != {
            "node_id",
            "action",
            "dependencies",
            "parallel_safe",
            "objective",
            "role",
            "lane",
            "read_scope",
            "write_scope",
            "acceptance",
            "hard_gates",
            "max_attempts",
        }:
            raise TournamentError("tournament node fields are invalid")
        node_id = raw.get("node_id")
        if not isinstance(node_id, str) or not node_id or node_id in by_id:
            raise TournamentError("tournament node ids must be unique non-empty strings")
        if not isinstance(raw.get("parallel_safe"), bool):
            raise TournamentError(f"node {node_id} lacks an exact parallel safety decision")
        if raw.get("action") not in allowed_actions:
            raise TournamentError(f"node {node_id} has an unsupported action")
        for field in ("objective",):
            if not isinstance(raw.get(field), str) or not raw[field].strip():
                raise TournamentError(f"node {node_id} lacks {field}")
        for field in ("read_scope", "write_scope", "acceptance", "hard_gates"):
            values = raw.get(field)
            if not isinstance(values, (list, tuple)) or not values or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                raise TournamentError(f"node {node_id} has an invalid {field}")
        if type(raw.get("max_attempts")) is not int or raw["max_attempts"] < 1:
            raise TournamentError(f"node {node_id} has an invalid attempt bound")
        by_id[node_id] = raw
    for node_id, raw in by_id.items():
        dependencies = raw.get("dependencies")
        if not isinstance(dependencies, (list, tuple)):
            raise TournamentError(f"node {node_id} dependencies are invalid")
        missing = set(dependencies) - set(by_id)
        if missing or node_id in dependencies:
            raise TournamentError(f"node {node_id} has invalid dependencies")

    role_nodes = {_role_node_id(role): role for role in TOURNAMENT_ROLES}
    feedback_nodes = {_feedback_node_id(role): role for role in TOURNAMENT_ROLES}
    component_actions = {
        "SYSTEM-STATIC": ("static-repository", "static"),
        "SYSTEM-LIFECYCLE": ("system-test", "lifecycle"),
        "SYSTEM-CODE-QA": ("system-test", "code-qa"),
        "SYSTEM-RESILIENCE": ("system-test", "resilience"),
        "SYSTEM-EVOLUTION": ("system-test", "evolution"),
        "SYSTEM-CONTROL-PLANE": ("control-plane-audit", "control-plane"),
    }
    expected_ids = {
        "SCAN-REPOSITORY",
        "SYSTEM-FULL-SUITE",
        "CROSS-EXAMINE",
        "CHAMPIONSHIP",
        *role_nodes,
        *feedback_nodes,
        *component_actions,
    }
    if set(by_id) != expected_ids:
        raise TournamentError("tournament plan node inventory is incomplete or unsupported")
    exact_contracts: dict[str, tuple[str, tuple[str, ...]]] = {
        "SCAN-REPOSITORY": ("inventory", ()),
        "SYSTEM-FULL-SUITE": ("full-suite", tuple(component_actions)),
        "CROSS-EXAMINE": ("cross-examine", ("SYSTEM-FULL-SUITE",)),
        "CHAMPIONSHIP": ("championship", tuple(feedback_nodes)),
    }
    exact_contracts.update(
        {node_id: ("grade-role", ("SCAN-REPOSITORY",)) for node_id in role_nodes}
    )
    exact_contracts.update(
        {node_id: (action, tuple(role_nodes)) for node_id, (action, _lane) in component_actions.items()}
    )
    exact_contracts.update(
        {
            node_id: ("feedback", (_role_node_id(role), "CROSS-EXAMINE"))
            for node_id, role in feedback_nodes.items()
        }
    )
    for node_id, (action, dependencies) in exact_contracts.items():
        raw = by_id[node_id]
        if raw["action"] != action or set(raw["dependencies"]) != set(dependencies):
            raise TournamentError(f"node {node_id} violates the canonical action topology")
    expected_parallel = {
        node_id: node_id in role_nodes or node_id in feedback_nodes or node_id in component_actions
        for node_id in expected_ids
    }
    expected_attempts = {
        node_id: 2 if node_id in role_nodes else 3 if node_id in feedback_nodes else 1
        for node_id in expected_ids
    }
    for node_id, raw in by_id.items():
        if raw["parallel_safe"] is not expected_parallel[node_id]:
            raise TournamentError(f"node {node_id} violates its canonical parallel decision")
        if raw["max_attempts"] != expected_attempts[node_id]:
            raise TournamentError(f"node {node_id} violates its canonical attempt bound")
    for node_id, role in role_nodes.items():
        if by_id[node_id].get("role") != role:
            raise TournamentError(f"node {node_id} has the wrong role binding")
    for node_id, role in feedback_nodes.items():
        if by_id[node_id].get("role") != role:
            raise TournamentError(f"node {node_id} has the wrong feedback role binding")
    for node_id, (_action, lane) in component_actions.items():
        if by_id[node_id].get("lane") != lane:
            raise TournamentError(f"node {node_id} has the wrong system lane binding")

    def ordered(predecessor: str, successor: str) -> bool:
        pending_dependencies = list(by_id[successor]["dependencies"])
        visited: set[str] = set()
        while pending_dependencies:
            current = pending_dependencies.pop()
            if current == predecessor:
                return True
            if current not in visited:
                visited.add(current)
                pending_dependencies.extend(by_id[current]["dependencies"])
        return False

    def scopes_overlap(left: str, right: str) -> bool:
        def base(value: str) -> str:
            return value[:-3] if value.endswith("/**") else value

        left_base, right_base = base(left), base(right)
        if left_base in {"*", "**", ""} or right_base in {"*", "**", ""}:
            return True
        if "*" in left_base or "*" in right_base:
            left_prefix = left_base.split("*", 1)[0]
            right_prefix = right_base.split("*", 1)[0]
            return (
                not left_prefix
                or not right_prefix
                or left_prefix.startswith(right_prefix)
                or right_prefix.startswith(left_prefix)
            )
        return (
            left_base == right_base
            or left_base.startswith(right_base.rstrip("/") + "/")
            or right_base.startswith(left_base.rstrip("/") + "/")
        )

    node_ids = sorted(by_id)
    for index, left_id in enumerate(node_ids):
        for right_id in node_ids[index + 1 :]:
            if not any(
                scopes_overlap(left, right)
                for left in by_id[left_id]["write_scope"]
                for right in by_id[right_id]["write_scope"]
            ):
                continue
            if not ordered(left_id, right_id) and not ordered(right_id, left_id):
                raise TournamentError(
                    f"unordered nodes {left_id} and {right_id} have overlapping write scopes"
                )

    pending = {node_id: set(raw["dependencies"]) for node_id, raw in by_id.items()}
    completed: set[str] = set()
    waves: list[tuple[str, ...]] = []
    limit = int(limit)
    while pending:
        ready = sorted(node_id for node_id, deps in pending.items() if deps <= completed)
        if not ready:
            raise TournamentError("tournament plan contains a cycle")
        serial = [node_id for node_id in ready if not by_id[node_id]["parallel_safe"]]
        wave = (serial[0],) if serial else tuple(ready[:limit])
        waves.append(wave)
        completed.update(wave)
        for node_id in wave:
            del pending[node_id]
    if canonical_digest(document) != canonical_digest(_canonical_plan_document()):
        raise TournamentError("tournament plan differs from the code-owned canonical contract")
    return tuple(waves)


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _is_link_like(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(is_junction is not None and is_junction())


def _has_link_like_component(root: Path, path: Path) -> bool:
    current = path
    while current != root:
        if _is_link_like(current):
            return True
        if current.parent == current:
            return True
        current = current.parent
    return _is_link_like(root)


def _reject_duplicate_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError(f"duplicate JSON object key: {key}")
        document[key] = value
    return document


def _strict_json_value(text: str, *, label: str) -> Any:
    try:
        return json.loads(text, object_pairs_hook=_reject_duplicate_object_pairs)
    except (json.JSONDecodeError, ValueError) as error:
        raise TournamentError(f"{label} contains invalid or ambiguous JSON") from error


def _read_json(path: Path) -> Mapping[str, Any]:
    value = _strict_json_value(path.read_text(encoding="utf-8"), label=str(path))
    if not isinstance(value, Mapping):
        raise TournamentError(f"JSON artifact must contain an object: {path}")
    return value


def _child_environment(repository: Path) -> dict[str, str]:
    """Build a small, credential-scrubbed environment for repository-owned checks.

    This is defense in depth, not a process or network sandbox.  The distinction is
    reported by the tournament and therefore cannot qualify a production agent.
    """

    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in _CHILD_OPTIONAL_ENV_NAMES
    }
    git_executable = _git_executable(repository)
    trusted_path = [str(Path(sys.executable).resolve().parent), str(git_executable.parent)]
    if os.name == "nt":
        windows = Path(environment.get("SYSTEMROOT", r"C:\Windows"))
        trusted_path.extend((str(windows / "System32"), str(windows)))
        environment["PATHEXT"] = ".COM;.EXE;.BAT;.CMD"
    else:
        trusted_path.extend(("/usr/bin", "/bin"))
    environment["PATH"] = os.pathsep.join(dict.fromkeys(trusted_path))
    environment.update(
        {
            "PYTHONPATH": os.pathsep.join(
                (
                    str(repository / "src"),
                    str(repository),
                    str(repository / ".autopilot/bin"),
                )
            ),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "PYTHONNOUSERSITE": "1",
            "PYTHONSAFEPATH": "1",
            "PYTHONUTF8": "1",
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "ALL_PROXY": "http://127.0.0.1:9",
            "NO_PROXY": "localhost,127.0.0.1,::1",
        }
    )
    return environment


def _git_environment(repository: Path) -> dict[str, str]:
    environment = _child_environment(repository)
    environment.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    return environment


def _git_executable(repository: Path) -> Path:
    del repository
    candidates = (
        (
            Path(r"C:\Program Files\Git\cmd\git.exe"),
            Path(r"C:\Program Files\Git\bin\git.exe"),
            Path(r"C:\Program Files (x86)\Git\cmd\git.exe"),
        )
        if os.name == "nt"
        else (Path("/usr/bin/git"), Path("/bin/git"))
    )
    for candidate in candidates:
        if not candidate.is_file() or candidate.is_symlink():
            continue
        executable = candidate.resolve()
        with executable.open("rb") as stream:
            prefix = stream.read(4)
        if os.name == "nt" and executable.suffix.casefold() == ".exe" and prefix[:2] == b"MZ":
            return executable
        if sys.platform.startswith("linux") and prefix == b"\x7fELF":
            return executable
        if sys.platform == "darwin" and prefix in {
            b"\xfe\xed\xfa\xce",
            b"\xfe\xed\xfa\xcf",
            b"\xca\xfe\xba\xbe",
            b"\xcf\xfa\xed\xfe",
        }:
            return executable
    raise TournamentError("a native Git executable in a fixed operating-system location is required")


def _bounded_subprocess(
    argv: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    timeout_seconds: int,
    max_stream_bytes: int,
) -> tuple[int | None, bytes, bytes, bool]:
    """Run with a wall-clock deadline and strict in-memory stream caps."""

    if timeout_seconds <= 0 or max_stream_bytes <= 0:
        raise TournamentError("subprocess resource budgets must be positive")
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    process = subprocess.Popen(
        tuple(argv),
        cwd=cwd,
        env=dict(environment),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=creationflags,
        start_new_session=os.name != "nt",
    )
    if process.stdout is None or process.stderr is None:
        process.kill()
        raise TournamentError("subprocess pipes were not created")
    overflow = threading.Event()
    buffers = {"stdout": bytearray(), "stderr": bytearray()}

    def drain(name: str, stream: Any) -> None:
        try:
            while chunk := stream.read(64 * 1024):
                remaining = max_stream_bytes - len(buffers[name])
                if remaining > 0:
                    buffers[name].extend(chunk[:remaining])
                if len(chunk) > remaining:
                    overflow.set()
        except (OSError, ValueError):
            overflow.set()

    readers = [
        threading.Thread(target=drain, args=("stdout", process.stdout), daemon=True),
        threading.Thread(target=drain, args=("stderr", process.stderr), daemon=True),
    ]
    for reader in readers:
        reader.start()

    def terminate_tree() -> None:
        if process.poll() is not None:
            return
        if os.name == "nt":
            windows = Path(environment.get("SYSTEMROOT", r"C:\Windows"))
            taskkill = windows / "System32/taskkill.exe"
            try:
                subprocess.run(
                    (str(taskkill), "/PID", str(process.pid), "/T", "/F"),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=10,
                )
            except (OSError, subprocess.SubprocessError):
                process.kill()
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                process.kill()

    deadline = time.monotonic() + timeout_seconds
    timed_out = False
    while process.poll() is None:
        if overflow.is_set():
            terminate_tree()
            break
        if time.monotonic() >= deadline:
            timed_out = True
            terminate_tree()
            break
        time.sleep(0.01)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)
    for reader in readers:
        reader.join(timeout=5)
    if any(reader.is_alive() for reader in readers):
        process.stdout.close()
        process.stderr.close()
        for reader in readers:
            reader.join(timeout=1)
        raise TournamentError("subprocess descendants retained an evidence stream")
    process.stdout.close()
    process.stderr.close()
    if overflow.is_set():
        raise TournamentError(
            "subprocess output exceeded the per-stream evidence budget "
            f"of {max_stream_bytes} bytes"
        )
    return (
        None if timed_out else process.returncode,
        bytes(buffers["stdout"]),
        bytes(buffers["stderr"]),
        timed_out,
    )


def _git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    argv = (
        str(_git_executable(repository)),
        "-c",
        "core.fsmonitor=false",
        "-c",
        f"core.hooksPath={os.devnull}",
        "-c",
        "core.pager=cat",
        "-C",
        str(repository),
        *arguments,
    )
    returncode, stdout, stderr, timed_out = _bounded_subprocess(
        argv,
        cwd=repository,
        environment=_git_environment(repository),
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
        max_stream_bytes=_MAX_GIT_STREAM_BYTES,
    )
    if timed_out or returncode is None:
        raise TimeoutError(f"Git command exceeded {_GIT_TIMEOUT_SECONDS} seconds")
    return subprocess.CompletedProcess(argv, returncode, stdout, stderr)


def inventory_repository(repository: str | Path, *, exclude: Path | None = None) -> dict[str, Any]:
    root = Path(repository).resolve()
    if not (root / "pyproject.toml").is_file() or not (root / "src/hive_mind_os").is_dir():
        raise TournamentError("repository does not contain the Hive Mind OS source package")
    top_level = _git(root, "rev-parse", "--show-toplevel")
    if top_level.returncode != 0:
        raise TournamentError("git could not resolve the repository root")
    try:
        observed_root = Path(top_level.stdout.decode("utf-8", errors="strict").strip()).resolve()
    except (OSError, UnicodeError, ValueError) as error:
        raise TournamentError("git returned an invalid repository root") from error
    if observed_root != root:
        raise TournamentError(
            f"git control plane is bound to {observed_root}, not requested root {root}"
        )
    deleted = _git(root, "ls-files", "--deleted", "-z")
    if deleted.returncode != 0:
        raise TournamentError("git could not inspect tracked deletions")
    missing_paths = sorted(
        value.decode("utf-8", errors="strict").replace("\\", "/")
        for value in deleted.stdout.split(b"\0")
        if value
    )
    if missing_paths:
        raise TournamentError(
            "repository contains tracked paths that cannot be inventoried: "
            + ", ".join(missing_paths)
        )
    listing = _git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    if listing.returncode != 0:
        raise TournamentError("git could not enumerate the repository")
    excluded_relative: str | None = None
    if exclude is not None:
        try:
            excluded_relative = exclude.resolve().relative_to(root).as_posix()
        except ValueError:
            excluded_relative = None
    files: list[dict[str, Any]] = []
    total_bytes = 0
    categories: dict[str, int] = {"source": 0, "tests": 0, "docs": 0, "other": 0}
    for raw in listing.stdout.split(b"\0"):
        if not raw:
            continue
        relative = raw.decode("utf-8", errors="strict").replace("\\", "/")
        if excluded_relative and (relative == excluded_relative or relative.startswith(excluded_relative + "/")):
            continue
        path = root / relative
        if _has_link_like_component(root, path):
            raise TournamentError(
                f"discovered repository path contains a symbolic link or junction: {relative}"
            )
        try:
            path.resolve().relative_to(root)
        except ValueError as error:
            raise TournamentError(f"discovered repository path escaped the root: {relative}") from error
        if not path.is_file():
            raise TournamentError(f"discovered repository path is not a regular file: {relative}")
        file_size = path.stat().st_size
        if file_size > _MAX_INVENTORY_FILE_BYTES:
            raise TournamentError(
                f"repository file exceeds the {_MAX_INVENTORY_FILE_BYTES}-byte evidence budget: "
                f"{relative}"
            )
        total_bytes += file_size
        if total_bytes > _MAX_INVENTORY_TOTAL_BYTES:
            raise TournamentError(
                "repository exceeds the aggregate inventory evidence budget of "
                f"{_MAX_INVENTORY_TOTAL_BYTES} bytes"
            )
        content = path.read_bytes()
        category = (
            "source" if relative.startswith("src/") else
            "tests" if relative.startswith("tests/") or relative.startswith(".autopilot/tests/") else
            "docs" if relative.startswith("docs/") or relative.startswith("USER_GUIDE/") else
            "other"
        )
        categories[category] += 1
        files.append(
            {"path": relative, "bytes": len(content), "sha256": _sha256_bytes(content), "category": category}
        )
    files.sort(key=lambda item: item["path"])
    discovered_paths = {str(item["path"]) for item in files}
    missing_required = sorted(_required_inventory_paths() - discovered_paths)
    if missing_required:
        raise TournamentError(
            "Git inventory omitted required tournament paths: " + ", ".join(missing_required)
        )
    head = _git(root, "rev-parse", "HEAD")
    branch = _git(root, "branch", "--show-current")
    status_arguments = ["status", "--porcelain=v1", "-z", "--untracked-files=all"]
    if excluded_relative:
        status_arguments.extend(
            (
                "--",
                ".",
                f":(exclude,literal){excluded_relative}",
                f":(exclude,glob){excluded_relative}/**",
            )
        )
    status = _git(root, *status_arguments)
    git_dir = _git(root, "rev-parse", "--absolute-git-dir")
    if any(result.returncode != 0 for result in (head, branch, status, git_dir)):
        raise TournamentError("Git could not seal HEAD, branch, status, and administrative state")
    try:
        head_value = head.stdout.decode("utf-8", errors="strict").strip()
        branch_value = branch.stdout.decode("utf-8", errors="strict").strip()
        git_directory = git_dir.stdout.decode("utf-8", errors="strict").strip()
    except UnicodeError as error:
        raise TournamentError("Git state contains non-UTF-8 control-plane output") from error
    if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", head_value) is None:
        raise TournamentError("Git returned an invalid HEAD object identifier")
    if not git_directory or not Path(git_directory).is_absolute():
        raise TournamentError("Git returned an invalid administrative directory")
    git_executable = _git_executable(root)
    document: dict[str, Any] = {
        "repository_root": str(root),
        "git_toplevel": str(observed_root),
        "git_directory": git_directory,
        "git_executable": {
            "path": str(git_executable),
            "sha256": _sha256_file(git_executable),
        },
        "head": head_value,
        "branch": branch_value,
        "dirty_path_count": len([item for item in status.stdout.split(b"\0") if item]),
        "file_count": len(files),
        "categories": categories,
        "files": files,
    }
    document["inventory_digest"] = canonical_digest(document)
    return document


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _observed_peak_concurrency(
    attempts: Mapping[str, Sequence[Mapping[str, Any]]],
) -> int:
    boundaries: list[tuple[datetime, int]] = []
    for rows in attempts.values():
        if not rows:
            continue
        try:
            started = datetime.fromisoformat(str(rows[0]["started_at"]).replace("Z", "+00:00"))
            ended = datetime.fromisoformat(str(rows[-1]["ended_at"]).replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError) as error:
            raise TournamentError("wave attempt timing is invalid") from error
        if started.tzinfo is None or ended.tzinfo is None or ended < started:
            raise TournamentError("wave attempt timing is impossible")
        if ended == started:
            continue
        boundaries.extend(((started, 1), (ended, -1)))
    active = 0
    peak = 0
    # Intervals are half-open.  At a shared boundary an ending attempt therefore
    # leaves before a new attempt enters; adjacency is not positive overlap.
    for _timestamp, change in sorted(boundaries, key=lambda item: (item[0], item[1])):
        active += change
        peak = max(peak, active)
    return peak


def _encode_command_transcript(stdout: bytes, stderr: bytes) -> str:
    return json.dumps(
        {
            "encoding": "base64",
            "schema_version": 1,
            "stderr": base64.b64encode(stderr).decode("ascii"),
            "stdout": base64.b64encode(stdout).decode("ascii"),
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _decode_command_transcript(transcript: str, *, label: str) -> tuple[bytes, bytes]:
    try:
        document = _strict_json_value(transcript, label=f"{label} transcript")
        if not isinstance(document, Mapping) or set(document) != {
            "encoding",
            "schema_version",
            "stderr",
            "stdout",
        }:
            raise ValueError("unexpected transcript fields")
        if (
            type(document["schema_version"]) is not int
            or document["schema_version"] != 1
            or document["encoding"] != "base64"
            or not isinstance(document["stdout"], str)
            or not isinstance(document["stderr"], str)
        ):
            raise ValueError("unsupported transcript envelope")
        stdout = base64.b64decode(document["stdout"], validate=True)
        stderr = base64.b64decode(document["stderr"], validate=True)
    except (binascii.Error, json.JSONDecodeError, TypeError, ValueError) as error:
        raise TournamentError(f"{label} transcript envelope is invalid") from error
    return stdout, stderr


def _unittest_observation(stdout: bytes, stderr: bytes) -> tuple[int | None, int, str | None, bool]:
    stdout_text = stdout.decode("utf-8", errors="replace")
    stderr_text = stderr.decode("utf-8", errors="replace")
    stdout_summaries = list(_UNITTEST_SUMMARY.finditer(stdout_text))
    stderr_summaries = list(_UNITTEST_SUMMARY.finditer(stderr_text))
    stdout_verdicts = list(_UNITTEST_VERDICT.finditer(stdout_text))
    stderr_verdicts = list(_UNITTEST_VERDICT.finditer(stderr_text))
    unambiguous = (
        not stdout_summaries
        and not stdout_verdicts
        and len(stderr_summaries) == 1
        and len(stderr_verdicts) == 1
        and stderr_summaries[0].start() < stderr_verdicts[0].start()
        and not stderr_text[stderr_verdicts[0].end() :].strip()
    )
    if not unambiguous:
        return None, 0, None, False
    count = int(stderr_summaries[0].group(1))
    verdict = "passed" if stderr_verdicts[0].group(1) == "OK" else "failed"
    details = stderr_verdicts[0].group(2) or ""
    skip_match = _SKIP_COUNT.search(details)
    skipped = int(skip_match.group(1)) if skip_match else 0
    return count, skipped, verdict, True


def _is_unittest_command(argv: Sequence[str]) -> bool:
    return any(tuple(argv[index : index + 2]) == ("-m", "unittest") for index in range(len(argv) - 1))


def run_command_receipt(
    repository: Path,
    argv: Sequence[str],
    *,
    timeout_seconds: int = 1800,
) -> tuple[dict[str, Any], str]:
    """Execute a local read/test command and return digest-only metadata plus transcript."""

    environment = _child_environment(repository)
    provenance_argv = (
        sys.executable,
        "-B",
        "-S",
        "-P",
        "-c",
        (
            "import importlib.util,pathlib;"
            "s=importlib.util.find_spec('hive_mind_os');"
            "print(pathlib.Path(s.origin).resolve() if s and s.origin else '')"
        ),
    )
    provenance_returncode, provenance_stdout, _provenance_stderr, provenance_timeout = (
        _bounded_subprocess(
            provenance_argv,
            cwd=repository,
            environment=environment,
            timeout_seconds=_PROVENANCE_TIMEOUT_SECONDS,
            max_stream_bytes=1024 * 1024,
        )
    )
    if provenance_timeout:
        raise TimeoutError(
            f"import provenance probe exceeded {_PROVENANCE_TIMEOUT_SECONDS} seconds"
        )
    try:
        resolved_package = provenance_stdout.decode("utf-8", errors="strict").strip()
    except UnicodeError as error:
        raise TournamentError("import provenance probe returned non-UTF-8 output") from error
    expected_package = (repository / "src/hive_mind_os").resolve()
    try:
        import_is_bound = (
            provenance_returncode == 0
            and Path(resolved_package).resolve().is_relative_to(expected_package)
        )
    except (OSError, ValueError):
        import_is_bound = False
    if not import_is_bound:
        raise TournamentError("child interpreter import path is not bound to this repository")
    started = _now()
    before = time.monotonic()
    returncode, stdout, stderr, timed_out = _bounded_subprocess(
        argv,
        cwd=repository,
        environment=environment,
        timeout_seconds=timeout_seconds,
        max_stream_bytes=_MAX_COMMAND_STREAM_BYTES,
    )
    ended = _now()
    duration_ms = round((time.monotonic() - before) * 1000)
    transcript = _encode_command_transcript(stdout, stderr)
    is_unittest = _is_unittest_command(argv)
    tests_run, tests_skipped, test_verdict, test_output_unambiguous = (
        _unittest_observation(stdout, stderr)
        if is_unittest
        else (None, 0, None, True)
    )
    command_passed = returncode == 0 and import_is_bound and not timed_out
    if is_unittest:
        command_passed = (
            command_passed
            and test_output_unambiguous
            and test_verdict == "passed"
            and tests_run is not None
            and tests_run > tests_skipped
        )
    receipt: dict[str, Any] = {
        "argv": list(argv),
        "started_at": started,
        "ended_at": ended,
        "duration_ms": duration_ms,
        "returncode": returncode,
        "timed_out": timed_out,
        "status": "passed" if command_passed else "failed",
        "resolved_package": resolved_package,
        "expected_package_root": str(expected_package),
        "import_provenance_bound": import_is_bound,
        "environment_policy": {
            "credential_environment_inherited": False,
            "inherited_git_variables": False,
            "git_configuration_isolation": "delegated to the repository code under test",
            "user_site_disabled": True,
            "network_control": "best-effort proxy deny; no kernel sandbox",
            "inherited_names": sorted(environment),
        },
        "test_output_unambiguous": test_output_unambiguous,
        "tests_run": tests_run,
        "tests_skipped": tests_skipped,
        "stdout_sha256": _sha256_bytes(stdout),
        "stderr_sha256": _sha256_bytes(stderr),
        "transcript_sha256": _sha256_bytes(transcript.encode("utf-8")),
    }
    receipt["receipt_digest"] = canonical_digest(receipt)
    return receipt, transcript


def _unittest_command(modules: Iterable[str]) -> tuple[str, ...]:
    return (sys.executable, "-B", "-m", "unittest", *tuple(modules), "-v")


def _criterion(
    criterion_id: str,
    earned: int,
    possible: int,
    evidence: Iterable[str],
    *,
    critical: bool = False,
    finding: str = "",
) -> dict[str, Any]:
    return {
        "criterion_id": criterion_id,
        "earned": earned,
        "possible": possible,
        "status": "pass" if earned == possible else "fail" if earned == 0 else "partial",
        "critical": critical,
        "evidence": list(evidence),
        "finding": finding,
    }


def _court(role: str, disposition: str, claims: Sequence[str], dissent: Sequence[str]) -> dict[str, Any]:
    if disposition not in DISPOSITIONS:
        raise TournamentError("unknown court disposition")
    identities = {
        "advocate": f"tournament:advocate:{role}",
        "cross_examiner": f"tournament:cross-examiner:{role}",
        "expert_witness": f"tournament:expert:{role}",
        "curator": f"tournament:curator:{role}",
        "judge": f"tournament:judge:{role}",
        "affected_champion": f"agent:{role}:current",
    }
    if len(set(identities.values())) != len(identities):
        raise TournamentError("court identities are not independent")
    return {
        "case_id": f"CASE-AGENT-{role.upper()}",
        "identities": identities,
        "identity_evidence": "declared separation only; independent processes/principals were not proven",
        "claims": list(claims),
        "dissent": list(dissent),
        "disposition": disposition,
        "promotion_authorized": False,
    }


def grade_role(
    repository: Path,
    role: str,
    command_runner: Callable[[Path, Sequence[str]], tuple[dict[str, Any], str]] = run_command_receipt,
) -> tuple[dict[str, Any], str]:
    if role not in ROLE_AUDIT_SPECS:
        raise TournamentError(f"unknown tournament role: {role}")
    spec = ROLE_AUDIT_SPECS[role]
    package = repository / "src/hive_mind_os/builtin_packages/hive-core"
    artifact_paths = {
        "agent": package / f"agents/{role}.json",
        "prompt": package / f"prompts/{role}.json",
        "skill": package / f"skills/{role}.json",
        "instructions": package / f"skills/instructions/{role}.json",
    }
    documents: dict[str, Mapping[str, Any]] = {}
    artifact_errors: list[str] = []
    for label, path in artifact_paths.items():
        try:
            documents[label] = _read_json(path)
        except (OSError, ValueError, json.JSONDecodeError, TournamentError) as error:
            artifact_errors.append(f"{label}: {type(error).__name__}: {error}")
    agent = documents.get("agent", {})
    prompt = documents.get("prompt", {})
    skill = documents.get("skill", {})
    instructions = documents.get("instructions", {})
    identity_valid = (
        agent.get("component_id") == f"agent.{role}"
        and agent.get("role_binding") == role
        and skill.get("component_id") == f"skill.{role}"
        and instructions.get("skill_id") == f"skill.{role}"
        and role in KERNEL_IMPLEMENTED_ROLES
        and Role(role) in ROLE_CONTRACTS
    )
    identity_evidence_valid = identity_valid and not artifact_errors
    outputs = agent.get("required_outputs", [])
    capabilities = agent.get("requested_capabilities", [])
    gates = agent.get("quality_gates", [])
    prompt_text = prompt.get("instructions", "")
    procedure = instructions.get("procedure", [])
    fail_closed = instructions.get("fail_closed_on", [])
    rich = (
        isinstance(outputs, list) and len(outputs) >= 3
        and isinstance(capabilities, list) and len(capabilities) >= 3
        and isinstance(gates, list) and len(gates) >= 2
        and isinstance(prompt_text, str) and len(prompt_text.split()) >= 10
        and isinstance(procedure, list) and len(procedure) >= 3
        and isinstance(fail_closed, list) and len(fail_closed) >= 2
    )
    implementation_ok = False
    implementation_error = ""
    implementation_path = (
        repository
        / "src"
        / Path(*spec.implementation_module.split("."))
    ).with_suffix(".py")
    try:
        implementation_path.resolve().relative_to(repository.resolve())
        implementation_tree = ast.parse(
            implementation_path.read_text(encoding="utf-8"),
            filename=str(implementation_path),
        )
        implementation_ok = any(
            isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == spec.implementation_symbol
            for node in implementation_tree.body
        )
        if not implementation_ok:
            implementation_error = (
                f"{spec.implementation_symbol} is not declared at module scope"
            )
    except (OSError, UnicodeError, SyntaxError, ValueError) as error:
        implementation_error = f"{type(error).__name__}: {error}"
    capability_contract = role_capabilities(role)
    boundary_ok = bool(capability_contract.required_outputs) and not (
        set(capability_contract.allowed_actions) & set(capability_contract.forbidden_actions)
    )
    repository_delivery_tier = (
        "limited-local" if role in _LIMITED_REPOSITORY_ROLES else "planned"
    )
    source_paths = {**artifact_paths, "implementation": implementation_path}
    source_bindings: dict[str, str | None] = {}
    for path in source_paths.values():
        relative = path.relative_to(repository).as_posix()
        try:
            source_bindings[relative] = _sha256_file(path)
        except OSError:
            source_bindings[relative] = None
    rubric_observations = {
        "identity_evidence_valid": identity_evidence_valid,
        "artifact_errors": artifact_errors,
        "rich_contract": rich,
        "implementation_declaration_present": implementation_ok,
        "implementation_error": implementation_error,
        "boundary_valid": boundary_ok,
        "fail_closed_count": len(fail_closed) if isinstance(fail_closed, list) else 0,
        "repository_delivery_tier": repository_delivery_tier,
        "source_bindings": source_bindings,
    }
    specialized_earned = (
        15 if implementation_ok and repository_delivery_tier == "limited-local"
        else 10 if implementation_ok
        else 0
    )
    test_receipt, transcript = command_runner(repository, _unittest_command(spec.test_modules))
    tests_ok = test_receipt["status"] == "passed" and bool(test_receipt.get("tests_run"))
    criteria = [
        _criterion(
            "registered-identity-and-artifacts",
            20 if identity_evidence_valid else 0,
            20,
            [path.relative_to(repository).as_posix() for path in artifact_paths.values()],
            critical=not identity_valid,
            finding="; ".join(artifact_errors),
        ),
        _criterion(
            "rich-role-contract",
            15 if rich else 5 if identity_evidence_valid else 0,
            15,
            [f"outputs={len(outputs) if isinstance(outputs, list) else 0}", f"capabilities={len(capabilities) if isinstance(capabilities, list) else 0}", f"quality_gates={len(gates) if isinstance(gates, list) else 0}"],
            finding="role contract needs richer outputs, instructions, or fail-closed behavior" if not rich else "",
        ),
        _criterion(
            "specialized-implementation-surface",
            specialized_earned,
            20,
            [
                f"{spec.implementation_module}:{spec.implementation_symbol}",
                "src/hive_mind_os/roles.py:IMPLEMENTED_REPOSITORY_ROLES",
                f"repository_delivery_tier={repository_delivery_tier}",
            ],
            finding=(
                implementation_error
                or (
                    "a limited local repository path exists, but arbitrary-repository and live-provider outcomes are unproven"
                    if repository_delivery_tier == "limited-local"
                    else "the implementation surface is declared, but the repository delivery role is explicitly planned"
                )
            ),
        ),
        _criterion(
            "provider-cognition-and-boundary",
            8 if boundary_ok else 0,
            15,
            ["hive_mind_os.brain_kernel.role_runtime:RoleRuntime", f"allowed={list(capability_contract.allowed_actions)}", f"forbidden={list(capability_contract.forbidden_actions)}"],
            critical=not boundary_ok,
            finding=(
                "allowed and forbidden capabilities overlap"
                if not boundary_ok
                else "provider cognition is structurally reachable but no live provider episode is executed by this offline tournament"
            ),
        ),
        _criterion(
            "independent-role-tests",
            25 if tests_ok else 0,
            25,
            [str(test_receipt["receipt_digest"]), *spec.test_modules],
            finding="role tests failed, timed out, or reported no executed tests" if not tests_ok else "",
        ),
        _criterion(
            "feedback-and-rollback-contract",
            3 if isinstance(fail_closed, list) and len(fail_closed) >= 2 else 0,
            5,
            [f"skills/instructions/{role}.json", "workflow.challenger-experiment"],
            finding=(
                "feedback path lacks explicit failure boundaries"
                if not fail_closed
                else "this run emits a challenger contract but does not implement or promote a successor"
            ),
        ),
    ]
    score = sum(item["earned"] for item in criteria)
    critical = [item for item in criteria if item["critical"] and item["status"] != "pass"]
    if critical:
        disposition = "quarantine"
    elif not tests_ok:
        disposition = "adapt"
    elif score >= 85:
        # Offline structural and fixture evidence is intentionally insufficient
        # for a claim that an agent is operationally complete.
        disposition = "adapt"
    elif score >= 60:
        disposition = "adapt"
    else:
        disposition = "defer"
    dissent = [item["finding"] for item in criteria if item["finding"]]
    claims = [
        (
            f"{role} registration and required artifacts validated"
            if identity_evidence_valid
            else f"{role} registration or required artifacts did not validate"
        ),
        (
                f"{role} declares a specialized implementation surface for: {spec.purpose}"
                if implementation_ok
                else f"{role} specialized implementation surface was not found for: {spec.purpose}"
        ),
        f"{role} focused tests {'passed' if tests_ok else 'did not pass'}",
    ]
    document: dict[str, Any] = {
        "role": role,
        "purpose": spec.purpose,
        "score": score,
        "possible": 100,
        "grade": "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 else "D" if score >= 60 else "F",
        "criteria": criteria,
        "rubric_observations": rubric_observations,
        "test_receipt": test_receipt,
        "fatal_findings": [item["finding"] or item["criterion_id"] for item in critical],
        "development_findings": dissent,
        "operational_dimensions": {
            "structural_contract": "tested" if tests_ok and identity_evidence_valid else "failed",
            "repository_delivery": repository_delivery_tier,
            "provider_backed_semantics": "unproven",
            "independent_end_to_end": "unproven",
            "production": "unproven",
        },
        "operationally_qualified": False,
        "qualification_limit": (
            "live-provider semantic tasks, independent principals, hostile-code isolation, "
            "and production outcomes were not supplied"
        ),
        "court": _court(role, disposition, claims, dissent),
    }
    document["grade_digest"] = canonical_digest(document)
    return document, transcript


def static_repository_gate(repository: Path, inventory: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    parsed = {"python": 0, "json": 0}
    for item in inventory["files"]:
        relative = str(item["path"])
        path = repository / relative
        try:
            content = path.read_bytes()
            if item.get("bytes") != len(content) or item.get("sha256") != _sha256_bytes(content):
                errors.append({"path": relative, "error": "content changed after repository seal"})
                continue
            if relative.endswith(".py"):
                ast.parse(content.decode("utf-8"), filename=relative)
                parsed["python"] += 1
            elif relative.endswith(".json"):
                _strict_json_value(content.decode("utf-8"), label=relative)
                parsed["json"] += 1
        except (OSError, UnicodeError, SyntaxError, json.JSONDecodeError, TournamentError) as error:
            errors.append({"path": relative, "error": f"{type(error).__name__}: {error}"})
    document: dict[str, Any] = {
        "lane": "static",
        "status": "passed" if not errors else "failed",
        "parsed": parsed,
        "errors": errors,
        "inventory_digest": inventory["inventory_digest"],
        "critical": bool(errors),
    }
    document["receipt_digest"] = canonical_digest(document)
    return document


def control_plane_gate(
    repository: Path,
    command_runner: Callable[[Path, Sequence[str]], tuple[dict[str, Any], str]] = run_command_receipt,
) -> tuple[dict[str, Any], str]:
    command = (
        sys.executable,
        "-B",
        ".autopilot/bin/dag_standard.py",
        "dag-lint",
        "--strict",
        "--plan",
        ".autopilot/plan.json",
        "--json",
    )
    receipt, transcript = command_runner(repository, command)
    document = {
        "lane": "control-plane",
        "status": receipt["status"],
        "critical": False,
        "interpretation": (
            "legacy control plane is strictly valid"
            if receipt["status"] == "passed"
            else "legacy control plane needs adaptation; this does not erase its retained ideas"
        ),
        "command_receipt": receipt,
    }
    document["receipt_digest"] = canonical_digest(document)
    return document, transcript


def _test_lane(
    repository: Path,
    lane: str,
    modules: Sequence[str],
    command_runner: Callable[[Path, Sequence[str]], tuple[dict[str, Any], str]] = run_command_receipt,
) -> tuple[dict[str, Any], str]:
    receipt, transcript = command_runner(repository, _unittest_command(modules))
    document = {
        "lane": lane,
        "status": receipt["status"],
        "critical": lane in {"lifecycle", "code-qa", "resilience"} and receipt["status"] != "passed",
        "test_modules": list(modules),
        "command_receipt": receipt,
    }
    document["receipt_digest"] = canonical_digest(document)
    return document, transcript


def _full_suite(repository: Path, enabled: bool) -> tuple[dict[str, Any], str | None]:
    if not enabled:
        document: dict[str, Any] = {
            "lane": "full-suite",
            "status": "deferred",
            "critical": False,
            "reason": "operator selected --skip-full-suite; no completeness claim is allowed",
        }
        document["receipt_digest"] = canonical_digest(document)
        return document, None
    return _full_discovery(repository)


def _full_discovery(repository: Path) -> tuple[dict[str, Any], str]:
    receipt, transcript = run_command_receipt(
        repository,
        (sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-v"),
        timeout_seconds=3600,
    )
    document = {
        "lane": "full-suite",
        "status": receipt["status"],
        "critical": receipt["status"] != "passed",
        "command_receipt": receipt,
    }
    document["receipt_digest"] = canonical_digest(document)
    return document, transcript


def cross_examine(
    receipts: Mapping[str, Mapping[str, Any]],
    repository: Path | None = None,
    *,
    exclude: Path | None = None,
) -> dict[str, Any]:
    fatal: list[str] = []
    gaps: list[str] = []
    for role in TOURNAMENT_ROLES:
        grade = receipts[_role_node_id(role)]
        fatal.extend(f"{role}: {value}" for value in grade.get("fatal_findings", ()))
        gaps.extend(f"{role}: {value}" for value in grade.get("development_findings", ()))
    for node_id, value in receipts.items():
        if not node_id.startswith("SYSTEM-"):
            continue
        status = value.get("status")
        if status != "passed":
            finding = f"{node_id}: {status}"
            (fatal if value.get("critical") else gaps).append(finding)
    if receipts.get("SYSTEM-CONTROL-PLANE", {}).get("status") != "passed":
        gaps.append("the installed predecessor DAG is not a releaseable strict-lint champion")
    gaps.extend(
        (
            "tournament court identities are declared labels, not separately authenticated principals",
            "repository checks are credential-scrubbed but lack a kernel-enforced filesystem/process/network sandbox",
            (
                "an interrupted tournament preserves self-hashed diagnostic remnants but must restart "
                "in a new create-only directory; only completed bundles are independently verified"
            ),
            "tournament events use a dedicated hash chain rather than the canonical KernelStore event spine",
        )
    )
    source_drift = False
    final_inventory_digest: str | None = None
    if repository is not None:
        mission_source = (repository / "src/hive_mind_os/brain_kernel/mission_runtime.py").read_text(encoding="utf-8")
        role_source = (repository / "src/hive_mind_os/brain_kernel/role_runtime.py").read_text(encoding="utf-8")
        adapter_source = (repository / "src/hive_mind_os/cortex/repository/mission_adapter.py").read_text(encoding="utf-8")
        if "for role in KERNEL_IMPLEMENTED_ROLES" in mission_source and "previous = work_id" in mission_source:
            gaps.append("canonical MissionRuntime still constructs and executes a serial all-role chain")
        if "class RoleExecutor(Protocol):\n    def execute" in mission_source and "async def execute" in role_source:
            gaps.append("provider RoleRuntime is async/effect-free while MissionRuntime still requires a synchronous executor")
        if '"app.txt"' in adapter_source and '"local-check"' in adapter_source:
            gaps.append("the local mission adapter remains a narrow app.txt/local-check fixture, not general repository execution")
        roles_source = (repository / "src/hive_mind_os/roles.py").read_text(encoding="utf-8")
        handler_source = (repository / "src/hive_mind_os/cortex/repository/role_handlers.py").read_text(encoding="utf-8")
        experiment_source = (repository / "src/hive_mind_os/experiment_runner.py").read_text(encoding="utf-8")
        legacy_verifier_source = (
            repository
            / "docs/execution/dags/generic-hive-mind-product-v3/verify_plan.py"
        ).read_text(encoding="utf-8")
        if "Only these roles have" in roles_source and "the remainder are planned" in roles_source:
            gaps.append("the authoritative repository lifecycle marks five of eight roles as planned")
        if "class _RepositoryRoleHandler" in handler_source and "effect execution is not enabled" in handler_source:
            gaps.append("all eight kernel roles share a generic local-only handler with effects disabled")
        if "evaluation surface not implemented" in experiment_source:
            gaps.append("the fixture experiment surface is disabled, so a real optimizer loop is not available")
        if (
            "stat_result.st_ctime_ns" in legacy_verifier_source
            and "def _git_executable_path_state" in legacy_verifier_source
        ):
            gaps.append(
                "the sealed V3 verifier uses unstable Windows/Python 3.14 Git-executable ctime; "
                "a governed successor must prefer birthtime and retain digest revalidation"
            )
        final_inventory = inventory_repository(repository, exclude=exclude)
        final_inventory_digest = str(final_inventory["inventory_digest"])
        initial = receipts["SCAN-REPOSITORY"]
        initial_content = canonical_digest(
            {"head": initial.get("head"), "files": initial.get("files")}
        )
        final_content = canonical_digest(
            {"head": final_inventory.get("head"), "files": final_inventory.get("files")}
        )
        source_drift = initial_content != final_content
        if source_drift:
            fatal.append("repository content changed between the opening seal and final cross-examination")
    document: dict[str, Any] = {
        "fatal_findings": sorted(set(fatal)),
        "development_gaps": sorted(set(gaps)),
        "attacks": [
            "A passing role test is not evidence of live-provider quality or customer value.",
            "A high average cannot compensate for a failed safety, identity, code-QA, or full-suite gate.",
            "The grading DAG proves parallel assessment, not yet parallel product mutation.",
            "A generated challenger may not mutate or promote its parent champion.",
        ],
        "dissent_preserved": True,
        "source_drift": source_drift,
        "final_inventory_digest": final_inventory_digest,
    }
    document["receipt_digest"] = canonical_digest(document)
    return document


def feedback_contract(
    role_grade: Mapping[str, Any],
    cross: Mapping[str, Any],
    *,
    max_cycles: int = 3,
) -> dict[str, Any]:
    if type(max_cycles) is not int or not 1 <= max_cycles <= 3:
        raise TournamentError("feedback cycle bound must be between one and three")
    role = str(role_grade["role"])
    findings = list(role_grade.get("fatal_findings", ())) + list(role_grade.get("development_findings", ()))
    system_findings = list(
        (*cross.get("fatal_findings", ()), *cross.get("development_gaps", ()))
    )
    hypotheses = [f"Resolve observed finding without weakening its acceptance gate: {item}" for item in findings]
    if not hypotheses:
        hypotheses = [
            f"Challenge {role} with an adversarial task outside its happy-path fixtures.",
            f"Measure {role} on live-provider output quality while retaining deterministic authority controls.",
        ]
    stages = (
        "reconsider-from-source-evidence",
        "attack-with-counterexamples",
        "seal-acceptance-rollback-and-reentry",
    )
    cycles: list[dict[str, Any]] = []
    cycle_hypotheses = list(hypotheses)
    for cycle_number, stage in enumerate(stages[:max_cycles], start=1):
        input_digest = canonical_digest(
            {
                "role_grade": role_grade["grade_digest"],
                "cross_examination": cross.get("receipt_digest"),
                "prior_hypotheses": cycle_hypotheses,
            }
        )
        if stage == "attack-with-counterexamples":
            cycle_hypotheses = [
                f"Find a falsifying counterexample before accepting: {hypothesis}"
                for hypothesis in cycle_hypotheses
            ]
        elif stage == "seal-acceptance-rollback-and-reentry":
            cycle_hypotheses = [
                f"Specify an executable acceptance test and rollback, then re-scan: {hypothesis}"
                for hypothesis in cycle_hypotheses
            ]
        cycle = {
            "cycle": cycle_number,
            "stage": stage,
            "input_digest": input_digest,
            "output_hypotheses": list(cycle_hypotheses),
            "champion_mutated": False,
            "promotion_authorized": False,
        }
        cycle["cycle_digest"] = canonical_digest(cycle)
        cycles.append(cycle)
    document: dict[str, Any] = {
        "role": role,
        "champion_ref": f"agent:{role}:current",
        "champion_grade_digest": role_grade["grade_digest"],
        "decision": "repair-before-retest" if role_grade["court"]["disposition"] != "adopt" else "retain-and-challenge",
        "initial_hypotheses": hypotheses,
        "challenger_hypotheses": cycle_hypotheses,
        "system_findings": system_findings,
        "changed_scope": [f"agent:{role}"],
        "immutable_champion": True,
        "promotion_authorized": False,
        "max_cycles": max_cycles,
        "cycles_executed": len(cycles),
        "cycles": cycles,
        "restart_nodes": ["SCAN-REPOSITORY", _role_node_id(role), "SYSTEM-LIFECYCLE", "SYSTEM-FULL-SUITE"],
        "reentry_execution": (
            "challenge synthesis is complete; materializing or evaluating a changed challenger "
            "requires a create-only tournament run from SCAN-REPOSITORY"
        ),
        "stop_conditions": [
            "independent role and system gates adopt the challenger",
            "three evidence-bearing cycles complete without material improvement",
            "a genuine human authority gate is reached",
        ],
        "rollback": f"retain agent:{role}:current and preserve every losing receipt",
    }
    document["feedback_digest"] = canonical_digest(document)
    return document


def championship(receipts: Mapping[str, Mapping[str, Any]], plan_digest: str) -> dict[str, Any]:
    roles = [receipts[_role_node_id(role)] for role in TOURNAMENT_ROLES]
    lanes = [
        receipts["SYSTEM-STATIC"],
        receipts["SYSTEM-LIFECYCLE"],
        receipts["SYSTEM-CODE-QA"],
        receipts["SYSTEM-RESILIENCE"],
        receipts["SYSTEM-EVOLUTION"],
        receipts["SYSTEM-CONTROL-PLANE"],
        receipts["SYSTEM-FULL-SUITE"],
    ]
    lane_weights = {
        "static": 15,
        "lifecycle": 20,
        "code-qa": 20,
        "resilience": 15,
        "evolution": 15,
        "control-plane": 5,
        "full-suite": 10,
    }
    system_score = sum(lane_weights[str(lane["lane"])] for lane in lanes if lane["status"] == "passed")
    role_average = round(sum(int(item["score"]) for item in roles) / len(roles), 2)
    cross = receipts["CROSS-EXAMINE"]
    fatal = list(cross["fatal_findings"])
    incomplete = [lane["lane"] for lane in lanes if lane["status"] != "passed"]
    if fatal:
        disposition = "quarantine"
    elif incomplete or any(item["court"]["disposition"] != "adopt" for item in roles):
        disposition = "adapt"
    elif system_score >= 90 and role_average >= 85:
        disposition = "adopt"
    else:
        disposition = "adapt"
    overall = round(role_average * 0.55 + system_score * 0.45, 2)
    claims = (
        "all eight constitutional roles received separately derived grades",
        "all seven composition lanes produced explicit non-compensating statuses",
        "feedback synthesis preserved champions and emitted create-only re-entry requirements",
    )
    dissent = tuple(cross["development_gaps"])
    court = _court("system", disposition, claims, dissent)
    report: dict[str, Any] = {
        "schema_version": 1,
        "kind": "hive-mind-agent-readiness-tournament-report",
        "plan_digest": plan_digest,
        "role_grades": [
            {
                "role": item["role"],
                "score": item["score"],
                "grade": item["grade"],
                "disposition": item["court"]["disposition"],
                "grade_digest": item["grade_digest"],
            }
            for item in roles
        ],
        "role_average": role_average,
        "system_score": system_score,
        "overall_score": overall,
        "system_lanes": [
            {"lane": lane["lane"], "status": lane["status"], "receipt_digest": lane["receipt_digest"]}
            for lane in lanes
        ],
        "fatal_findings": fatal,
        "development_gaps": list(cross["development_gaps"]),
        "court": court,
        "selected_candidate": "current bounded hybrid plus agent-readiness-tournament-v1",
        "comparison": {
            "status": "not-run",
            "winner": None,
            "reason": "no equal-budget, pinned multi-comparator benchmark was executed",
        },
        "qualification": (
            "This is repository-readiness evidence from declared court roles, not proof of "
            "independent principals, live-provider quality, production safety, or superiority."
        ),
        "feedback_digests": [receipts[_feedback_node_id(role)]["feedback_digest"] for role in TOURNAMENT_ROLES],
        "repository": {
            "head": receipts["SCAN-REPOSITORY"]["head"],
            "branch": receipts["SCAN-REPOSITORY"]["branch"],
            "dirty_path_count": receipts["SCAN-REPOSITORY"]["dirty_path_count"],
            "file_count": receipts["SCAN-REPOSITORY"]["file_count"],
            "inventory_digest": receipts["SCAN-REPOSITORY"]["inventory_digest"],
        },
        "execution": receipts["SCAN-REPOSITORY"]["execution"],
    }
    report["report_digest"] = canonical_digest(report)
    return report


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _render_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Agent readiness tournament",
        "",
        f"- Verdict: **{str(report['court']['disposition']).upper()}**",
        f"- Independent-role average: **{report['role_average']}/100**",
        f"- Whole-system score: **{report['system_score']}/100**",
        f"- Combined score: **{report['overall_score']}/100**",
        f"- Report digest: `{report['report_digest']}`",
        "",
        "## Independent role grades",
        "",
        "| Role | Score | Grade | Court disposition |",
        "|---|---:|:---:|---|",
    ]
    for grade in report["role_grades"]:
        lines.append(f"| {grade['role']} | {grade['score']} | {grade['grade']} | {grade['disposition']} |")
    lines.extend(("", "## Whole-system lanes", "", "| Lane | Status |", "|---|---|"))
    for lane in report["system_lanes"]:
        lines.append(f"| {lane['lane']} | {lane['status']} |")
    lines.extend(("", "## Preserved gaps", ""))
    gaps = report["fatal_findings"] + report["development_gaps"]
    lines.extend(f"- {value}" for value in gaps)
    if not gaps:
        lines.append("- No repository-evidence gap was observed; live-provider and customer-value proof remain outside this run.")
    lines.extend(("", "## Qualification", "", str(report["qualification"]), ""))
    return "\n".join(lines)


def _write_markdown(path: Path, report: Mapping[str, Any]) -> None:
    path.write_text(_render_markdown(report), encoding="utf-8")


def _manifest(run_dir: Path) -> dict[str, Any]:
    files = []
    total_bytes = 0
    for path in sorted(run_dir.rglob("*")):
        if _is_link_like(path):
            raise TournamentError("run evidence may not contain symbolic links or junctions")
        if path.is_dir():
            if path.relative_to(run_dir).as_posix() not in {
                "receipts",
                "transcripts",
                "waves",
            }:
                raise TournamentError("run evidence contains an unknown directory")
            continue
        if path.is_file() and path != run_dir / "manifest.json":
            size = path.stat().st_size
            total_bytes += size
            if size > _MAX_RUN_ARTIFACT_BYTES or total_bytes > _MAX_RUN_TOTAL_BYTES:
                raise TournamentError("run evidence exceeded its artifact budget")
            files.append(
                {
                    "path": path.relative_to(run_dir).as_posix(),
                    "bytes": size,
                    "sha256": _sha256_file(path),
                }
            )
        elif path != run_dir / "manifest.json":
            raise TournamentError("run evidence contains an unsupported filesystem entry")
    document: dict[str, Any] = {"schema_version": 1, "files": files}
    document["manifest_digest"] = canonical_digest(document)
    return document


def _validate_command_receipt(
    receipt: Mapping[str, Any],
    expected_argv: Sequence[str],
    transcript: str,
    repository_root: Path,
    *,
    require_tests: bool,
    label: str,
) -> None:
    expected_fields = {
        "argv",
        "started_at",
        "ended_at",
        "duration_ms",
        "returncode",
        "timed_out",
        "status",
        "resolved_package",
        "expected_package_root",
        "import_provenance_bound",
        "environment_policy",
        "test_output_unambiguous",
        "tests_run",
        "tests_skipped",
        "stdout_sha256",
        "stderr_sha256",
        "transcript_sha256",
        "receipt_digest",
    }
    if set(receipt) != expected_fields:
        raise TournamentError(f"{label} command receipt fields are invalid")
    if receipt.get("argv") != list(expected_argv):
        raise TournamentError(f"{label} executed an unexpected command")
    if receipt.get("status") not in {"passed", "failed"}:
        raise TournamentError(f"{label} command status is invalid")
    if not isinstance(receipt.get("timed_out"), bool):
        raise TournamentError(f"{label} timeout evidence is invalid")
    returncode = receipt.get("returncode")
    if returncode is not None and type(returncode) is not int:
        raise TournamentError(f"{label} return-code evidence is invalid")
    if receipt["timed_out"] is not (returncode is None):
        raise TournamentError(f"{label} timeout and return-code evidence conflict")
    if receipt.get("import_provenance_bound") is not True:
        raise TournamentError(f"{label} import provenance is invalid")
    base_passed = (
        receipt.get("returncode") == 0
        and receipt["import_provenance_bound"]
        and not receipt["timed_out"]
    )
    if type(receipt.get("tests_skipped")) is not int or receipt["tests_skipped"] < 0:
        raise TournamentError(f"{label} skipped-test evidence is invalid")
    tests_run = receipt.get("tests_run")
    if tests_run is not None and (type(tests_run) is not int or tests_run < 0):
        raise TournamentError(f"{label} test-count evidence is invalid")
    try:
        started = datetime.fromisoformat(str(receipt["started_at"]).replace("Z", "+00:00"))
        ended = datetime.fromisoformat(str(receipt["ended_at"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError) as error:
        raise TournamentError(f"{label} command timing is invalid") from error
    duration_ms = receipt.get("duration_ms")
    now = datetime.now(UTC)
    if (
        started.tzinfo is None
        or ended.tzinfo is None
        or ended < started
        or ended > now.replace(microsecond=0) + timedelta(minutes=5)
        or type(duration_ms) is not int
        or duration_ms < 0
    ):
        raise TournamentError(f"{label} command timing is impossible")
    elapsed_ms = (ended - started).total_seconds() * 1000
    if abs(duration_ms - elapsed_ms) > 2_000:
        raise TournamentError(f"{label} wall and monotonic durations conflict")
    expected_package_root = (repository_root / "src/hive_mind_os").resolve()
    try:
        recorded_expected_root = Path(str(receipt["expected_package_root"])).resolve()
    except (KeyError, OSError, ValueError) as error:
        raise TournamentError(f"{label} expected package root is invalid") from error
    if recorded_expected_root != expected_package_root:
        raise TournamentError(f"{label} expected package root is not bound to the repository")
    try:
        resolved_package = Path(str(receipt["resolved_package"])).resolve()
    except (KeyError, OSError, ValueError) as error:
        raise TournamentError(f"{label} resolved package is invalid") from error
    if resolved_package != (expected_package_root / "__init__.py").resolve():
        raise TournamentError(f"{label} resolved package escaped the repository")
    environment_policy = receipt.get("environment_policy")
    if (
        not isinstance(environment_policy, Mapping)
        or set(environment_policy)
        != {
            "credential_environment_inherited",
            "inherited_git_variables",
            "git_configuration_isolation",
            "user_site_disabled",
            "network_control",
            "inherited_names",
        }
        or environment_policy.get("credential_environment_inherited") is not False
        or environment_policy.get("inherited_git_variables") is not False
        or environment_policy.get("user_site_disabled") is not True
        or environment_policy.get("git_configuration_isolation")
        != "delegated to the repository code under test"
        or environment_policy.get("network_control")
        != "best-effort proxy deny; no kernel sandbox"
    ):
        raise TournamentError(f"{label} child-environment evidence is invalid")
    available_names = environment_policy.get("inherited_names")
    allowed_names = _CHILD_OPTIONAL_ENV_NAMES | _CHILD_REQUIRED_ENV_NAMES
    if os.name == "nt":
        allowed_names = allowed_names | {"PATHEXT"}
    if (
        not isinstance(available_names, list)
        or any(not isinstance(name, str) for name in available_names)
        or available_names != sorted(set(available_names))
        or not _CHILD_REQUIRED_ENV_NAMES <= {name.upper() for name in available_names}
        or not {name.upper() for name in available_names} <= allowed_names
    ):
        raise TournamentError(f"{label} child-environment name inventory is invalid")
    for field in ("transcript_sha256",):
        if not isinstance(receipt.get(field), str) or _DIGEST.fullmatch(receipt[field]) is None:
            raise TournamentError(f"{label} lacks a valid {field}")
    stdout, stderr = _decode_command_transcript(transcript, label=label)
    if len(stdout) > _MAX_COMMAND_STREAM_BYTES or len(stderr) > _MAX_COMMAND_STREAM_BYTES:
        raise TournamentError(f"{label} transcript exceeds its per-stream evidence budget")
    if (
        receipt.get("transcript_sha256") != _sha256_bytes(transcript.encode("utf-8"))
        or receipt.get("stdout_sha256") != _sha256_bytes(stdout)
        or receipt.get("stderr_sha256") != _sha256_bytes(stderr)
    ):
        raise TournamentError(f"{label} stdout/stderr hashes do not match its transcript")
    if require_tests:
        observed_count, observed_skips, verdict, unambiguous = _unittest_observation(
            stdout, stderr
        )
        if unambiguous:
            if (
                receipt.get("test_output_unambiguous") is not True
                or receipt.get("tests_run") != observed_count
                or receipt.get("tests_skipped") != observed_skips
            ):
                raise TournamentError(f"{label} test totals do not match its transcript")
            substantive_tests = (
                type(observed_count) is int and observed_count > observed_skips
            )
            expected_status = (
                "passed"
                if base_passed and verdict == "passed" and substantive_tests
                else "failed"
            )
        else:
            # A crash or timeout may legitimately end before unittest emits a
            # summary.  Preserve that adverse evidence, but never award credit.
            if (
                receipt.get("test_output_unambiguous") is not False
                or receipt.get("tests_run") is not None
                or receipt.get("tests_skipped") != 0
                or receipt.get("status") != "failed"
                or base_passed
            ):
                raise TournamentError(f"{label} test totals do not match its transcript")
            expected_status = "failed"
    else:
        if (
            receipt.get("test_output_unambiguous") is not True
            or receipt.get("tests_run") is not None
            or receipt.get("tests_skipped") != 0
        ):
            raise TournamentError(f"{label} non-test command contains test claims")
        expected_status = "passed" if base_passed else "failed"
    if receipt["status"] != expected_status:
        raise TournamentError(f"{label} command status is not derivable")


def _validate_scan_receipt(scan: Mapping[str, Any]) -> None:
    if set(scan) != {
        "repository_root",
        "git_toplevel",
        "git_directory",
        "git_executable",
        "head",
        "branch",
        "dirty_path_count",
        "file_count",
        "categories",
        "files",
        "execution",
        "inventory_digest",
    }:
        raise TournamentError("repository scan fields are invalid")
    root = scan.get("repository_root")
    if not isinstance(root, str) or not Path(root).is_absolute() or scan.get("git_toplevel") != root:
        raise TournamentError("repository scan is not bound to one absolute Git top-level")
    files = scan.get("files")
    if (
        not isinstance(files, list)
        or type(scan.get("file_count")) is not int
        or scan["file_count"] != len(files)
    ):
        raise TournamentError("repository scan file inventory is invalid")
    paths: list[str] = []
    total_bytes = 0
    categories = {"source": 0, "tests": 0, "docs": 0, "other": 0}
    for row in files:
        if not isinstance(row, Mapping) or set(row) != {
            "path",
            "bytes",
            "sha256",
            "category",
        }:
            raise TournamentError("repository scan contains a malformed file row")
        path = row.get("path")
        category = row.get("category")
        if (
            not isinstance(path, str)
            or not path
            or Path(path).is_absolute()
            or path != Path(path).as_posix()
            or ".." in Path(path).parts
            or type(row.get("bytes")) is not int
            or row["bytes"] < 0
            or not isinstance(row.get("sha256"), str)
            or _DIGEST.fullmatch(row["sha256"]) is None
            or category not in categories
        ):
            raise TournamentError("repository scan contains an invalid file row")
        if row["bytes"] > _MAX_INVENTORY_FILE_BYTES:
            raise TournamentError("repository scan exceeds its per-file evidence budget")
        total_bytes += row["bytes"]
        paths.append(path)
        categories[str(category)] += 1
    if total_bytes > _MAX_INVENTORY_TOTAL_BYTES:
        raise TournamentError("repository scan exceeds its aggregate evidence budget")
    supplied_categories = scan.get("categories")
    if (
        not isinstance(supplied_categories, Mapping)
        or set(supplied_categories) != set(categories)
        or any(type(value) is not int or value < 0 for value in supplied_categories.values())
        or paths != sorted(set(paths))
        or supplied_categories != categories
    ):
        raise TournamentError("repository scan paths or category totals are invalid")
    missing_required = sorted(_required_inventory_paths() - set(paths))
    if missing_required:
        raise TournamentError(
            "repository scan omitted required tournament paths: "
            + ", ".join(missing_required)
        )
    if (
        not isinstance(scan.get("head"), str)
        or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", scan["head"]) is None
        or not isinstance(scan.get("branch"), str)
        or type(scan.get("dirty_path_count")) is not int
        or scan["dirty_path_count"] < 0
        or not isinstance(scan.get("git_directory"), str)
        or not Path(scan["git_directory"]).is_absolute()
    ):
        raise TournamentError("repository scan Git state is invalid")
    git_executable = scan.get("git_executable")
    if (
        not isinstance(git_executable, Mapping)
        or set(git_executable) != {"path", "sha256"}
        or not isinstance(git_executable.get("path"), str)
        or not Path(git_executable["path"]).is_absolute()
        or not isinstance(git_executable.get("sha256"), str)
        or _DIGEST.fullmatch(git_executable["sha256"]) is None
    ):
        raise TournamentError("repository scan Git executable evidence is invalid")
    execution = scan.get("execution")
    if not isinstance(execution, Mapping):
        raise TournamentError("repository scan lacks execution provenance")
    if (
        set(execution)
        != {
            "runner_identity",
            "trusted_builtin_runner",
            "runtime_path",
            "runtime_sha256",
        }
        or not isinstance(execution.get("runner_identity"), str)
        or not isinstance(execution.get("trusted_builtin_runner"), bool)
        or execution.get("runtime_path") != "src/hive_mind_os/agent_tournament.py"
        or not isinstance(execution.get("runtime_sha256"), str)
        or _DIGEST.fullmatch(execution["runtime_sha256"]) is None
    ):
        raise TournamentError("repository scan execution provenance is invalid")
    if execution["trusted_builtin_runner"] and execution["runner_identity"] != (
        f"{run_command_receipt.__module__}:{run_command_receipt.__qualname__}"
    ):
        raise TournamentError("repository scan falsely claims the built-in runner")


def _validate_role_grade(
    role: str,
    grade: Mapping[str, Any],
    transcript: str,
    scan: Mapping[str, Any],
) -> None:
    spec = ROLE_AUDIT_SPECS[role]
    repository_root = Path(str(scan["repository_root"]))
    if set(grade) != {
        "role",
        "purpose",
        "score",
        "possible",
        "grade",
        "criteria",
        "rubric_observations",
        "test_receipt",
        "fatal_findings",
        "development_findings",
        "operational_dimensions",
        "operationally_qualified",
        "qualification_limit",
        "court",
        "grade_digest",
    }:
        raise TournamentError(f"role {role} grade fields are invalid")
    if grade.get("role") != role or grade.get("purpose") != spec.purpose:
        raise TournamentError(f"role grade is bound to the wrong role: {role}")
    test_receipt = grade.get("test_receipt")
    if not isinstance(test_receipt, Mapping):
        raise TournamentError(f"role {role} lacks a command receipt")
    _validate_command_receipt(
        test_receipt,
        _unittest_command(spec.test_modules),
        transcript,
        repository_root,
        require_tests=True,
        label=f"role {role}",
    )
    criteria = grade.get("criteria")
    if not isinstance(criteria, list) or any(not isinstance(row, Mapping) for row in criteria):
        raise TournamentError(f"role {role} criteria are invalid")
    by_id = {str(row.get("criterion_id")): row for row in criteria}
    possible = {
        "registered-identity-and-artifacts": 20,
        "rich-role-contract": 15,
        "specialized-implementation-surface": 20,
        "provider-cognition-and-boundary": 15,
        "independent-role-tests": 25,
        "feedback-and-rollback-contract": 5,
    }
    if len(by_id) != len(criteria) or set(by_id) != set(possible):
        raise TournamentError(f"role {role} criterion inventory is invalid")
    observations = grade.get("rubric_observations")
    expected_observation_fields = {
        "identity_evidence_valid",
        "artifact_errors",
        "rich_contract",
        "implementation_declaration_present",
        "implementation_error",
        "boundary_valid",
        "fail_closed_count",
        "repository_delivery_tier",
        "source_bindings",
    }
    if not isinstance(observations, Mapping) or set(observations) != expected_observation_fields:
        raise TournamentError(f"role {role} rubric observations are invalid")
    boolean_fields = (
        "identity_evidence_valid",
        "rich_contract",
        "implementation_declaration_present",
        "boundary_valid",
    )
    if any(not isinstance(observations.get(field), bool) for field in boolean_fields):
        raise TournamentError(f"role {role} rubric observations are not typed")
    artifact_errors = observations.get("artifact_errors")
    implementation_error = observations.get("implementation_error")
    fail_closed_count = observations.get("fail_closed_count")
    repository_delivery_tier = (
        "limited-local" if role in _LIMITED_REPOSITORY_ROLES else "planned"
    )
    if (
        not isinstance(artifact_errors, list)
        or any(not isinstance(value, str) for value in artifact_errors)
        or not isinstance(implementation_error, str)
        or type(fail_closed_count) is not int
        or fail_closed_count < 0
        or observations.get("repository_delivery_tier") != repository_delivery_tier
    ):
        raise TournamentError(f"role {role} rubric observations are inconsistent")
    package_prefix = "src/hive_mind_os/builtin_packages/hive-core"
    expected_source_paths = {
        f"{package_prefix}/agents/{role}.json",
        f"{package_prefix}/prompts/{role}.json",
        f"{package_prefix}/skills/{role}.json",
        f"{package_prefix}/skills/instructions/{role}.json",
        "src/" + spec.implementation_module.replace(".", "/") + ".py",
    }
    source_bindings = observations.get("source_bindings")
    inventory_hashes = {
        str(row.get("path")): row.get("sha256")
        for row in scan.get("files", ())
        if isinstance(row, Mapping)
    }
    if (
        not isinstance(source_bindings, Mapping)
        or set(source_bindings) != expected_source_paths
        or any(
            not isinstance(digest, str)
            or _DIGEST.fullmatch(digest) is None
            or inventory_hashes.get(path) != digest
            for path, digest in source_bindings.items()
        )
    ):
        raise TournamentError(f"role {role} source observations are not inventory-bound")
    specialized_credit = 15 if role in _LIMITED_REPOSITORY_ROLES else 10
    identity_ok = bool(observations["identity_evidence_valid"])
    rich = bool(observations["rich_contract"])
    implementation_ok = bool(observations["implementation_declaration_present"])
    boundary_ok = bool(observations["boundary_valid"])
    tests_ok = test_receipt["status"] == "passed" and bool(test_receipt.get("tests_run"))
    expected_earned = {
        "registered-identity-and-artifacts": 20 if identity_ok else 0,
        "rich-role-contract": 15 if rich else 5 if identity_ok else 0,
        "specialized-implementation-surface": specialized_credit if implementation_ok else 0,
        "provider-cognition-and-boundary": 8 if boundary_ok else 0,
        "independent-role-tests": 25 if tests_ok else 0,
        "feedback-and-rollback-contract": 3 if fail_closed_count >= 2 else 0,
    }
    expected_findings = {
        "registered-identity-and-artifacts": "; ".join(artifact_errors),
        "rich-role-contract": (
            "role contract needs richer outputs, instructions, or fail-closed behavior"
            if not rich
            else ""
        ),
        "specialized-implementation-surface": (
            implementation_error
            or (
                "a limited local repository path exists, but arbitrary-repository and live-provider outcomes are unproven"
                if repository_delivery_tier == "limited-local"
                else "the implementation surface is declared, but the repository delivery role is explicitly planned"
            )
        ),
        "provider-cognition-and-boundary": (
            "allowed and forbidden capabilities overlap"
            if not boundary_ok
            else "provider cognition is structurally reachable but no live provider episode is executed by this offline tournament"
        ),
        "independent-role-tests": (
            "" if tests_ok else "role tests failed, timed out, or reported no executed tests"
        ),
        "feedback-and-rollback-contract": (
            "feedback path lacks explicit failure boundaries"
            if fail_closed_count == 0
            else "this run emits a challenger contract but does not implement or promote a successor"
        ),
    }
    for criterion_id, row in by_id.items():
        earned = row.get("earned")
        if (
            set(row)
            != {
                "criterion_id",
                "earned",
                "possible",
                "status",
                "critical",
                "evidence",
                "finding",
            }
            or type(earned) is not int
            or type(row.get("possible")) is not int
            or row.get("possible") != possible[criterion_id]
            or earned != expected_earned[criterion_id]
            or row.get("finding") != expected_findings[criterion_id]
            or not isinstance(row.get("evidence"), list)
            or any(not isinstance(value, str) for value in row["evidence"])
        ):
            raise TournamentError(f"role {role} criterion is not derivable from its rubric")
        expected_status = "pass" if earned == row["possible"] else "fail" if earned == 0 else "partial"
        if row.get("status") != expected_status:
            raise TournamentError(f"role {role} criterion status is not derivable")
    for criterion_id, row in by_id.items():
        expected_critical = criterion_id in {
            "registered-identity-and-artifacts",
            "provider-cognition-and-boundary",
        } and row["earned"] == 0
        if row.get("critical") is not expected_critical:
            raise TournamentError(f"role {role} critical-gate status is not derivable")
    score = sum(int(row["earned"]) for row in criteria)
    expected_grade = (
        "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70
        else "D" if score >= 60 else "F"
    )
    if (
        type(grade.get("score")) is not int
        or grade["score"] != score
        or type(grade.get("possible")) is not int
        or grade["possible"] != 100
        or grade.get("grade") != expected_grade
    ):
        raise TournamentError(f"role {role} aggregate score is not derivable")
    critical = [row for row in criteria if row["critical"] and row["status"] != "pass"]
    disposition = "quarantine" if critical else "adapt" if (not tests_ok or score >= 60) else "defer"
    dissent = [str(row.get("finding", "")) for row in criteria if row.get("finding")]
    fatal = [str(row.get("finding") or row["criterion_id"]) for row in critical]
    expected_court = _court(
        role,
        disposition,
        (
            (
                f"{role} registration and required artifacts validated"
                if by_id["registered-identity-and-artifacts"]["earned"] == 20
                else f"{role} registration or required artifacts did not validate"
            ),
            (
                f"{role} declares a specialized implementation surface for: {spec.purpose}"
                if by_id["specialized-implementation-surface"]["earned"] > 0
                else f"{role} specialized implementation surface was not found for: {spec.purpose}"
            ),
            f"{role} focused tests {'passed' if tests_ok else 'did not pass'}",
        ),
        dissent,
    )
    expected_dimensions = {
        "structural_contract": (
            "tested"
            if tests_ok and by_id["registered-identity-and-artifacts"]["earned"] == 20
            else "failed"
        ),
        "repository_delivery": (
            repository_delivery_tier
        ),
        "provider_backed_semantics": "unproven",
        "independent_end_to_end": "unproven",
        "production": "unproven",
    }
    if (
        grade.get("fatal_findings") != fatal
        or grade.get("development_findings") != dissent
        or canonical_digest(grade.get("court")) != canonical_digest(expected_court)
        or grade.get("operational_dimensions") != expected_dimensions
        or grade.get("operationally_qualified") is not False
        or grade.get("qualification_limit")
        != (
            "live-provider semantic tasks, independent principals, hostile-code isolation, "
            "and production outcomes were not supplied"
        )
    ):
        raise TournamentError(f"role {role} disposition or qualification is not derivable")

    def replay_command(
        _repository: Path, argv: Sequence[str]
    ) -> tuple[dict[str, Any], str]:
        if list(argv) != list(test_receipt["argv"]):
            raise TournamentError(f"role {role} source re-derivation requested another command")
        return dict(test_receipt), transcript

    expected_grade, _expected_transcript = grade_role(
        repository_root,
        role,
        replay_command,
    )
    if canonical_digest(grade) != canonical_digest(expected_grade):
        raise TournamentError(f"role {role} grade is not derivable from the sealed checkout")


def _validate_system_receipt(
    node_id: str,
    receipt: Mapping[str, Any],
    scan: Mapping[str, Any],
    transcript: str | None,
) -> None:
    repository_root = Path(str(scan["repository_root"]))
    if node_id == "SYSTEM-STATIC":
        if set(receipt) != {
            "lane",
            "status",
            "parsed",
            "errors",
            "inventory_digest",
            "critical",
            "receipt_digest",
        }:
            raise TournamentError("static system receipt fields are invalid")
        errors = receipt.get("errors")
        parsed = receipt.get("parsed")
        expected_file_counts = {
            "python": sum(str(row.get("path", "")).endswith(".py") for row in scan["files"]),
            "json": sum(str(row.get("path", "")).endswith(".json") for row in scan["files"]),
        }
        if (
            not isinstance(errors, list)
            or any(
                not isinstance(row, Mapping)
                or set(row) != {"path", "error"}
                or row.get("path") not in {item.get("path") for item in scan["files"]}
                or not isinstance(row.get("error"), str)
                for row in errors
            )
            or not isinstance(parsed, Mapping)
            or set(parsed) != {"python", "json"}
            or any(type(parsed.get(kind)) is not int for kind in expected_file_counts)
            or any(not 0 <= parsed[kind] <= total for kind, total in expected_file_counts.items())
            or (not errors and parsed != expected_file_counts)
            or receipt.get("lane") != "static"
            or receipt.get("inventory_digest") != scan.get("inventory_digest")
            or receipt.get("status") != ("passed" if not errors else "failed")
            or receipt.get("critical") is not bool(errors)
        ):
            raise TournamentError("static system receipt is not derivable")
        expected_receipt = static_repository_gate(repository_root, scan)
        if canonical_digest(receipt) != canonical_digest(expected_receipt):
            raise TournamentError("static system receipt is not derivable from the sealed checkout")
        return
    if node_id == "SYSTEM-FULL-SUITE":
        if receipt.get("status") == "deferred":
            if (
                set(receipt)
                != {"lane", "status", "critical", "reason", "receipt_digest"}
                or receipt.get("lane") != "full-suite"
                or receipt.get("critical") is not False
                or receipt.get("reason")
                != "operator selected --skip-full-suite; no completeness claim is allowed"
                or "command_receipt" in receipt
            ):
                raise TournamentError("deferred full-suite receipt is invalid")
            return
        command = receipt.get("command_receipt")
        if not isinstance(command, Mapping) or transcript is None:
            raise TournamentError("full-suite pass/failure lacks command evidence")
        if set(receipt) != {
            "lane",
            "status",
            "critical",
            "command_receipt",
            "receipt_digest",
        }:
            raise TournamentError("full-suite receipt fields are invalid")
        _validate_command_receipt(
            command,
            (sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-v"),
            transcript,
            repository_root,
            require_tests=True,
            label="full-suite",
        )
        if (
            receipt.get("lane") != "full-suite"
            or receipt.get("status") != command["status"]
            or receipt.get("critical") is not (command["status"] != "passed")
        ):
            raise TournamentError("full-suite receipt is not derivable")
        return
    lane_by_node = {
        "SYSTEM-LIFECYCLE": "lifecycle",
        "SYSTEM-CODE-QA": "code-qa",
        "SYSTEM-RESILIENCE": "resilience",
        "SYSTEM-EVOLUTION": "evolution",
        "SYSTEM-CONTROL-PLANE": "control-plane",
    }
    lane = lane_by_node[node_id]
    command = receipt.get("command_receipt")
    if not isinstance(command, Mapping) or transcript is None:
        raise TournamentError(f"{lane} lane lacks command evidence")
    expected_fields = {
        "lane",
        "status",
        "critical",
        "command_receipt",
        "receipt_digest",
    }
    if lane == "control-plane":
        expected_fields.add("interpretation")
    else:
        expected_fields.add("test_modules")
    if set(receipt) != expected_fields:
        raise TournamentError(f"{lane} system receipt fields are invalid")
    expected_argv = (
        (
            sys.executable,
            "-B",
            ".autopilot/bin/dag_standard.py",
            "dag-lint",
            "--strict",
            "--plan",
            ".autopilot/plan.json",
            "--json",
        )
        if lane == "control-plane"
        else _unittest_command(SYSTEM_TEST_LANES[lane])
    )
    _validate_command_receipt(
        command,
        expected_argv,
        transcript,
        repository_root,
        require_tests=lane != "control-plane",
        label=lane,
    )
    expected_critical = lane in {"lifecycle", "code-qa", "resilience"} and command["status"] != "passed"
    expected_interpretation = (
        "legacy control plane is strictly valid"
        if command["status"] == "passed"
        else "legacy control plane needs adaptation; this does not erase its retained ideas"
    )
    if (
        receipt.get("lane") != lane
        or receipt.get("status") != command["status"]
        or receipt.get("critical") is not expected_critical
        or (
            lane == "control-plane"
            and receipt.get("interpretation") != expected_interpretation
        )
        or (
            lane != "control-plane"
            and receipt.get("test_modules") != list(SYSTEM_TEST_LANES[lane])
        )
    ):
        raise TournamentError(f"{lane} system receipt is not derivable")


def _validate_cross_receipt(
    cross: Mapping[str, Any], receipts: Mapping[str, Mapping[str, Any]]
) -> None:
    expected_fields = {
        "fatal_findings",
        "development_gaps",
        "attacks",
        "dissent_preserved",
        "source_drift",
        "final_inventory_digest",
        "receipt_digest",
    }
    if set(cross) != expected_fields:
        raise TournamentError("cross-examination fields are invalid")
    fatal = cross.get("fatal_findings")
    gaps = cross.get("development_gaps")
    if (
        not isinstance(fatal, list)
        or not isinstance(gaps, list)
        or any(not isinstance(value, str) for value in (*fatal, *gaps))
    ):
        raise TournamentError("cross-examination findings are invalid")
    if fatal != sorted(set(fatal)) or gaps != sorted(set(gaps)):
        raise TournamentError("cross-examination findings are not canonical")
    required_fatal: set[str] = set()
    required_gaps: set[str] = {
        "all eight kernel roles share a generic local-only handler with effects disabled",
        "tournament court identities are declared labels, not separately authenticated principals",
        "repository checks are credential-scrubbed but lack a kernel-enforced filesystem/process/network sandbox",
        (
            "an interrupted tournament preserves self-hashed diagnostic remnants but must restart "
            "in a new create-only directory; only completed bundles are independently verified"
        ),
        "tournament events use a dedicated hash chain rather than the canonical KernelStore event spine",
        "canonical MissionRuntime still constructs and executes a serial all-role chain",
        "provider RoleRuntime is async/effect-free while MissionRuntime still requires a synchronous executor",
        "the local mission adapter remains a narrow app.txt/local-check fixture, not general repository execution",
        "the authoritative repository lifecycle marks five of eight roles as planned",
        "the fixture experiment surface is disabled, so a real optimizer loop is not available",
        (
            "the sealed V3 verifier uses unstable Windows/Python 3.14 Git-executable ctime; "
            "a governed successor must prefer birthtime and retain digest revalidation"
        ),
    }
    for role in TOURNAMENT_ROLES:
        grade = receipts[_role_node_id(role)]
        required_fatal.update(f"{role}: {value}" for value in grade["fatal_findings"])
        required_gaps.update(f"{role}: {value}" for value in grade["development_findings"])
    for node_id, value in receipts.items():
        if node_id.startswith("SYSTEM-") and value.get("status") != "passed":
            finding = f"{node_id}: {value.get('status')}"
            (required_fatal if value.get("critical") else required_gaps).add(finding)
    if receipts["SYSTEM-CONTROL-PLANE"].get("status") != "passed":
        required_gaps.add("the installed predecessor DAG is not a releaseable strict-lint champion")
    drift_finding = "repository content changed between the opening seal and final cross-examination"
    if cross.get("source_drift") is True:
        required_fatal.add(drift_finding)
    elif drift_finding in fatal or cross.get("source_drift") is not False:
        raise TournamentError("cross-examination drift evidence is inconsistent")
    if set(fatal) != required_fatal or set(gaps) != required_gaps:
        raise TournamentError("cross-examination adverse evidence is not exact")
    if cross.get("dissent_preserved") is not True:
        raise TournamentError("cross-examination does not preserve dissent")
    expected_attacks = [
        "A passing role test is not evidence of live-provider quality or customer value.",
        "A high average cannot compensate for a failed safety, identity, code-QA, or full-suite gate.",
        "The grading DAG proves parallel assessment, not yet parallel product mutation.",
        "A generated challenger may not mutate or promote its parent champion.",
    ]
    if cross.get("attacks") != expected_attacks:
        raise TournamentError("cross-examination attacks are not canonical")
    final_inventory_digest = cross.get("final_inventory_digest")
    if (
        not isinstance(final_inventory_digest, str)
        or _DIGEST.fullmatch(final_inventory_digest) is None
    ):
        raise TournamentError("cross-examination final inventory is invalid")
    opening_inventory = dict(receipts["SCAN-REPOSITORY"])
    opening_inventory.pop("execution", None)
    opening_inventory.pop("inventory_digest", None)
    unchanged_final_digest = canonical_digest(opening_inventory)
    if (
        (cross["source_drift"] is False and final_inventory_digest != unchanged_final_digest)
        or (cross["source_drift"] is True and final_inventory_digest == unchanged_final_digest)
    ):
        raise TournamentError("cross-examination final inventory is not drift-bound")


def verify_run_directory(
    run_directory: str | Path,
    *,
    repository: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(run_directory).resolve()
    manifest_path = root / "manifest.json"
    if (
        not manifest_path.is_file()
        or _is_link_like(manifest_path)
        or manifest_path.stat().st_size > _MAX_RUN_ARTIFACT_BYTES
    ):
        raise TournamentError("run manifest is missing or exceeds its evidence budget")
    manifest = _read_json(manifest_path)
    if set(manifest) != {"schema_version", "files", "manifest_digest"}:
        raise TournamentError("run manifest fields are invalid")
    if type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1:
        raise TournamentError("run manifest schema is invalid")
    material = dict(manifest)
    supplied = material.pop("manifest_digest", None)
    if supplied != canonical_digest(material):
        raise TournamentError("run manifest digest is invalid")
    manifest_rows = manifest.get("files")
    if not isinstance(manifest_rows, list):
        raise TournamentError("run manifest file inventory is invalid")
    listed_path_rows = [str(item.get("path")) for item in manifest_rows if isinstance(item, Mapping)]
    if len(listed_path_rows) != len(manifest_rows) or len(set(listed_path_rows)) != len(listed_path_rows):
        raise TournamentError("run manifest contains invalid or duplicate paths")
    listed_paths = set(listed_path_rows)
    observed_entries = list(root.rglob("*"))
    if any(_is_link_like(path) for path in observed_entries):
        raise TournamentError("run evidence contains a symbolic link or junction")
    observed_directories = {
        path.relative_to(root).as_posix()
        for path in observed_entries
        if path.is_dir()
    }
    if observed_directories != {"receipts", "transcripts", "waves"}:
        raise TournamentError("run evidence directory contract is invalid")
    if any(not path.is_file() and not path.is_dir() for path in observed_entries):
        raise TournamentError("run evidence contains an unsupported filesystem entry")
    observed_files = [
        path
        for path in observed_entries
        if path.is_file() and path != root / "manifest.json"
    ]
    observed_paths = {path.relative_to(root).as_posix() for path in observed_files}
    if listed_paths != observed_paths:
        missing = sorted(observed_paths - listed_paths)
        extra = sorted(listed_paths - observed_paths)
        raise TournamentError(
            f"run manifest inventory mismatch: unlisted={missing}, missing={extra}"
        )
    total_bytes = 0
    for item in manifest_rows:
        if not isinstance(item, Mapping) or set(item) != {"path", "bytes", "sha256"}:
            raise TournamentError("run manifest file row is invalid")
        path = root / str(item["path"])
        if (
            type(item.get("bytes")) is not int
            or item["bytes"] < 0
            or item["bytes"] > _MAX_RUN_ARTIFACT_BYTES
            or not isinstance(item.get("sha256"), str)
            or _DIGEST.fullmatch(item["sha256"]) is None
        ):
            raise TournamentError(f"run artifact metadata is invalid: {item.get('path')}")
        total_bytes += item["bytes"]
        if total_bytes > _MAX_RUN_TOTAL_BYTES:
            raise TournamentError("run evidence exceeds its aggregate artifact budget")
        if (
            not path.is_file()
            or path.stat().st_size != item["bytes"]
            or _sha256_file(path) != item["sha256"]
        ):
            raise TournamentError(f"run artifact does not match manifest: {item['path']}")
    plan = _read_json(root / "plan.json")
    waves = validate_tournament_plan(plan)
    report = _read_json(root / "report.json")
    if set(report) != {
        "schema_version",
        "kind",
        "plan_digest",
        "role_grades",
        "role_average",
        "system_score",
        "overall_score",
        "system_lanes",
        "fatal_findings",
        "development_gaps",
        "court",
        "selected_candidate",
        "comparison",
        "qualification",
        "feedback_digests",
        "repository",
        "execution",
        "report_digest",
    }:
        raise TournamentError("report fields are invalid")
    report_material = dict(report)
    report_digest = report_material.pop("report_digest", None)
    if report_digest != canonical_digest(report_material):
        raise TournamentError("report digest is invalid")
    if report.get("kind") != "hive-mind-agent-readiness-tournament-report":
        raise TournamentError("report kind is invalid")
    if report.get("plan_digest") != plan.get("plan_digest"):
        raise TournamentError("report is not bound to the executed plan")

    required_receipts = {
        "SCAN-REPOSITORY",
        "SYSTEM-STATIC",
        "SYSTEM-LIFECYCLE",
        "SYSTEM-CODE-QA",
        "SYSTEM-RESILIENCE",
        "SYSTEM-EVOLUTION",
        "SYSTEM-CONTROL-PLANE",
        "SYSTEM-FULL-SUITE",
        "CROSS-EXAMINE",
        "CHAMPIONSHIP",
        *(_role_node_id(role) for role in TOURNAMENT_ROLES),
        *(_feedback_node_id(role) for role in TOURNAMENT_ROLES),
    }
    receipt_paths = {path.stem for path in (root / "receipts").glob("*.json")}
    if receipt_paths != required_receipts:
        raise TournamentError("run receipt inventory is incomplete or contains unknown receipts")

    def validate_digest(document: Mapping[str, Any], field: str, label: str) -> None:
        value = document.get(field)
        unsigned = dict(document)
        unsigned.pop(field, None)
        if not isinstance(value, str) or _DIGEST.fullmatch(value) is None or value != canonical_digest(unsigned):
            raise TournamentError(f"{label} digest is invalid")

    receipts: dict[str, Mapping[str, Any]] = {}
    command_transcripts: dict[str, str] = {}
    for node_id in sorted(required_receipts):
        value = _read_json(root / "receipts" / f"{node_id}.json")
        digest_field = (
            "inventory_digest" if node_id == "SCAN-REPOSITORY" else
            "grade_digest" if node_id.startswith("ROLE-") else
            "feedback_digest" if node_id.startswith("FEEDBACK-") else
            "report_digest" if node_id == "CHAMPIONSHIP" else
            "receipt_digest"
        )
        validate_digest(value, digest_field, node_id)
        nested = value.get("test_receipt") or value.get("command_receipt")
        if isinstance(nested, Mapping):
            validate_digest(nested, "receipt_digest", f"{node_id} command")
            transcript_path = root / "transcripts" / f"{node_id}.txt"
            if not transcript_path.is_file() or _sha256_bytes(transcript_path.read_bytes()) != nested.get("transcript_sha256"):
                raise TournamentError(f"{node_id} transcript is not bound to its command receipt")
            command_transcripts[node_id] = transcript_path.read_bytes().decode("utf-8")
        receipts[node_id] = value

    expected_artifacts = {
        "plan.json",
        "report.json",
        "report.md",
        "events.jsonl",
        *(f"receipts/{node_id}.json" for node_id in required_receipts),
        *(f"waves/wave-{index:02d}.json" for index in range(1, len(waves) + 1)),
        *(f"transcripts/{node_id}.txt" for node_id in command_transcripts),
    }
    if listed_paths != expected_artifacts:
        unexpected = sorted(listed_paths - expected_artifacts)
        missing = sorted(expected_artifacts - listed_paths)
        raise TournamentError(
            f"run artifact contract mismatch: unexpected={unexpected}, missing={missing}"
        )

    _validate_scan_receipt(receipts["SCAN-REPOSITORY"])
    trusted_repository = Path(repository if repository is not None else Path.cwd()).resolve()
    recorded_repository = Path(
        str(receipts["SCAN-REPOSITORY"]["repository_root"])
    ).resolve()
    if trusted_repository != recorded_repository:
        raise TournamentError(
            "run evidence is not bound to the caller-selected repository checkout"
        )
    execution = receipts["SCAN-REPOSITORY"]["execution"]
    selected_runtime = (
        trusted_repository / str(execution["runtime_path"])
    ).resolve()
    loaded_runtime = Path(__file__).resolve()
    if (
        loaded_runtime != selected_runtime
        or _sha256_file(loaded_runtime) != execution["runtime_sha256"]
    ):
        raise TournamentError(
            "verifier runtime is not the recorded runtime from the caller-selected checkout"
        )
    for role in TOURNAMENT_ROLES:
        node_id = _role_node_id(role)
        _validate_role_grade(
            role,
            receipts[node_id],
            command_transcripts[node_id],
            receipts["SCAN-REPOSITORY"],
        )
    for node_id in (
        "SYSTEM-STATIC",
        "SYSTEM-LIFECYCLE",
        "SYSTEM-CODE-QA",
        "SYSTEM-RESILIENCE",
        "SYSTEM-EVOLUTION",
        "SYSTEM-CONTROL-PLANE",
        "SYSTEM-FULL-SUITE",
    ):
        _validate_system_receipt(
            node_id,
            receipts[node_id],
            receipts["SCAN-REPOSITORY"],
            command_transcripts.get(node_id),
        )
    _validate_cross_receipt(receipts["CROSS-EXAMINE"], receipts)

    live_inventory = inventory_repository(trusted_repository, exclude=root)
    opening_inventory = dict(receipts["SCAN-REPOSITORY"])
    opening_inventory.pop("execution", None)
    opening_inventory.pop("inventory_digest", None)
    sealed_content_digest = canonical_digest(opening_inventory)
    if live_inventory.get("inventory_digest") != sealed_content_digest:
        raise TournamentError("caller-selected repository differs from the sealed checkout")
    if (
        receipts["CROSS-EXAMINE"].get("final_inventory_digest")
        != live_inventory["inventory_digest"]
    ):
        raise TournamentError("cross-examination is not bound to the caller-selected checkout")

    if receipts["CHAMPIONSHIP"] != report:
        raise TournamentError("final report differs from the championship receipt")
    execution = receipts["SCAN-REPOSITORY"].get("execution")
    if not isinstance(execution, Mapping) or report.get("execution") != execution:
        raise TournamentError("report execution provenance is incomplete")
    runtime_rows = [
        item
        for item in receipts["SCAN-REPOSITORY"].get("files", ())
        if isinstance(item, Mapping) and item.get("path") == execution.get("runtime_path")
    ]
    if len(runtime_rows) != 1 or runtime_rows[0].get("sha256") != execution.get("runtime_sha256"):
        raise TournamentError("runner identity is not bound to the repository inventory")
    role_summaries = report.get("role_grades")
    if not isinstance(role_summaries, list) or {item.get("role") for item in role_summaries if isinstance(item, Mapping)} != set(TOURNAMENT_ROLES):
        raise TournamentError("report does not summarize exactly all eight roles")
    for summary in role_summaries:
        if not isinstance(summary, Mapping):
            raise TournamentError("report contains a malformed role summary")
        role = str(summary["role"])
        if summary.get("grade_digest") != receipts[_role_node_id(role)].get("grade_digest"):
            raise TournamentError(f"report role summary is stale: {role}")
    expected_feedback = [receipts[_feedback_node_id(role)]["feedback_digest"] for role in TOURNAMENT_ROLES]
    if report.get("feedback_digests") != expected_feedback:
        raise TournamentError("report feedback bindings are incomplete")
    for role in TOURNAMENT_ROLES:
        expected_contract = feedback_contract(
            receipts[_role_node_id(role)],
            receipts["CROSS-EXAMINE"],
            max_cycles=int(plan["feedback_policy"]["max_cycles"]),
        )
        if receipts[_feedback_node_id(role)] != expected_contract:
            raise TournamentError(f"feedback receipt is not derivable for role {role}")
    expected_report = championship(receipts, str(plan["plan_digest"]))
    if report != expected_report:
        raise TournamentError("championship report is not derivable from its source receipts")
    markdown_path = root / "report.md"
    if not markdown_path.is_file() or markdown_path.read_text(encoding="utf-8") != _render_markdown(report):
        raise TournamentError("human-readable report differs from the derived championship report")

    wave_files = sorted((root / "waves").glob("wave-*.json"))
    if len(wave_files) != len(waves):
        raise TournamentError("run wave inventory does not match the plan")
    executed_order: list[str] = []
    for index, (path, expected_wave) in enumerate(zip(wave_files, waves), start=1):
        wave = _read_json(path)
        if (
            set(wave)
            != {
                "wave",
                "nodes",
                "parallel",
                "workers_used",
                "status",
                "attempts",
                "observed_peak_concurrency",
                "observed_peak_command_concurrency",
            }
            or type(wave.get("wave")) is not int
            or wave["wave"] != index
            or tuple(wave.get("nodes", ())) != expected_wave
            or wave.get("status") != "completed"
        ):
            raise TournamentError(f"executed wave {index} differs from the plan")
        expected_parallel = len(expected_wave) > 1
        if wave.get("parallel") is not expected_parallel:
            raise TournamentError(f"executed wave {index} has false parallel provenance")
        expected_workers = 1 if len(expected_wave) == 1 else wave.get("workers_used")
        if (
            type(wave.get("workers_used")) is not int
            or not 1 <= wave["workers_used"] <= min(len(expected_wave), int(plan["max_parallelism"]))
            or (expected_parallel and wave["workers_used"] < 2)
            or (not expected_parallel and expected_workers != 1)
        ):
            raise TournamentError(f"executed wave {index} has invalid worker provenance")
        attempts = wave.get("attempts")
        if not isinstance(attempts, Mapping) or set(attempts) != set(expected_wave):
            raise TournamentError(f"executed wave {index} attempt evidence is incomplete")
        for node_id in expected_wave:
            attempt_rows = attempts[node_id]
            node = next(item for item in plan["nodes"] if item["node_id"] == node_id)
            if (
                not isinstance(attempt_rows, list)
                or not attempt_rows
                or any(not isinstance(row, Mapping) for row in attempt_rows)
                or len(attempt_rows) > node["max_attempts"]
                or attempt_rows[-1].get("outcome") != "completed"
                or [row.get("attempt") for row in attempt_rows]
                != list(range(1, len(attempt_rows) + 1))
            ):
                raise TournamentError(f"executed node {node_id} has invalid attempt evidence")
            expected_receipt_status = receipts[node_id].get("status", "completed")
            for attempt_index, row in enumerate(attempt_rows):
                is_final = attempt_index == len(attempt_rows) - 1
                expected_fields = (
                    {
                        "attempt",
                        "outcome",
                        "receipt_status",
                        "started_at",
                        "ended_at",
                        "duration_ms",
                    }
                    if is_final
                    else {
                        "attempt",
                        "outcome",
                        "error",
                        "started_at",
                        "ended_at",
                        "duration_ms",
                    }
                )
                if set(row) != expected_fields:
                    raise TournamentError(
                        f"executed node {node_id} has invalid attempt fields"
                    )
                if type(row.get("attempt")) is not int:
                    raise TournamentError(
                        f"executed node {node_id} has invalid attempt number"
                    )
                if is_final:
                    if (
                        row.get("outcome") != "completed"
                        or row.get("receipt_status") != expected_receipt_status
                    ):
                        raise TournamentError(
                            f"executed node {node_id} final attempt is not receipt-bound"
                        )
                elif (
                    row.get("outcome") != "infrastructure-exception"
                    or not isinstance(row.get("error"), str)
                    or not row["error"]
                ):
                    raise TournamentError(
                        f"executed node {node_id} contains a non-retryable retry"
                    )
                try:
                    started = datetime.fromisoformat(
                        str(row["started_at"]).replace("Z", "+00:00")
                    )
                    ended = datetime.fromisoformat(
                        str(row["ended_at"]).replace("Z", "+00:00")
                    )
                except (KeyError, TypeError, ValueError) as error:
                    raise TournamentError(
                        f"executed node {node_id} has invalid attempt timing"
                    ) from error
                duration_ms = row.get("duration_ms")
                if (
                    started.tzinfo is None
                    or ended.tzinfo is None
                    or ended < started
                    or type(duration_ms) is not int
                    or duration_ms < 0
                    or abs(duration_ms - (ended - started).total_seconds() * 1000)
                    > 60_000
                ):
                    raise TournamentError(
                        f"executed node {node_id} has impossible attempt timing"
                    )
            nested_command = receipts[node_id].get("test_receipt") or receipts[
                node_id
            ].get("command_receipt")
            if isinstance(nested_command, Mapping):
                try:
                    command_started = datetime.fromisoformat(
                        str(nested_command["started_at"]).replace("Z", "+00:00")
                    )
                    command_ended = datetime.fromisoformat(
                        str(nested_command["ended_at"]).replace("Z", "+00:00")
                    )
                    attempt_started = datetime.fromisoformat(
                        str(attempt_rows[-1]["started_at"]).replace("Z", "+00:00")
                    )
                    attempt_ended = datetime.fromisoformat(
                        str(attempt_rows[-1]["ended_at"]).replace("Z", "+00:00")
                    )
                except (KeyError, TypeError, ValueError) as error:
                    raise TournamentError(
                        f"executed node {node_id} command timing is invalid"
                    ) from error
                if not (
                    attempt_started <= command_started <= command_ended <= attempt_ended
                ):
                    raise TournamentError(
                        f"executed node {node_id} command is not enclosed by its final attempt"
                    )
        observed_peak = _observed_peak_concurrency(attempts)
        if (
            type(wave.get("observed_peak_concurrency")) is not int
            or wave["observed_peak_concurrency"] != observed_peak
        ):
            raise TournamentError(f"executed wave {index} concurrency evidence is stale")
        command_attempts = {
            node_id: [
                {
                    "started_at": nested["started_at"],
                    "ended_at": nested["ended_at"],
                }
            ]
            for node_id in expected_wave
            if isinstance(
                nested := receipts[node_id].get("test_receipt")
                or receipts[node_id].get("command_receipt"),
                Mapping,
            )
        }
        observed_command_peak = _observed_peak_concurrency(command_attempts)
        if (
            type(wave.get("observed_peak_command_concurrency")) is not int
            or wave["observed_peak_command_concurrency"] != observed_command_peak
        ):
            raise TournamentError(
                f"executed wave {index} command-concurrency evidence is stale"
            )
        if index in {2, 3} and observed_peak < 2:
            raise TournamentError(f"executed wave {index} did not demonstrate concurrency")
        if index in {2, 3} and observed_command_peak < 2:
            raise TournamentError(
                f"executed wave {index} did not demonstrate command concurrency"
            )
        executed_order.extend(expected_wave)

    event_lines = (root / "events.jsonl").read_text(encoding="utf-8").splitlines()
    if len(event_lines) != len(executed_order):
        raise TournamentError("event count does not match executed nodes")
    previous: str | None = None
    for sequence, (line, node_id) in enumerate(zip(event_lines, executed_order), start=1):
        event = _strict_json_value(line, label=f"event {sequence}")
        if not isinstance(event, dict) or set(event) != {
            "sequence",
            "node_id",
            "status",
            "receipt_digest",
            "previous_event_digest",
            "event_digest",
        }:
            raise TournamentError(f"event fields are invalid at sequence {sequence}")
        digest = event.pop("event_digest", None)
        if (
            type(event.get("sequence")) is not int
            or event["sequence"] != sequence
            or event.get("node_id") != node_id
            or event.get("status") != "completed"
            or event.get("previous_event_digest") != previous
            or digest != canonical_digest(event)
        ):
            raise TournamentError(f"event chain is invalid at sequence {sequence}")
        expected_receipt = (
            receipts[node_id].get("receipt_digest")
            or receipts[node_id].get("grade_digest")
            or receipts[node_id].get("feedback_digest")
            or receipts[node_id].get("inventory_digest")
            or receipts[node_id].get("report_digest")
        )
        if event.get("receipt_digest") != expected_receipt:
            raise TournamentError(f"event receipt binding is invalid at sequence {sequence}")
        previous = digest
    return {
        "status": "verified",
        "manifest_digest": supplied,
        "plan_digest": plan["plan_digest"],
        "report_digest": report_digest,
        "disposition": report["court"]["disposition"],
        "trusted_builtin_runner": bool(execution.get("trusted_builtin_runner")),
        "verification_scope": (
            "schema, source-semantic derivation against the caller-selected exact checkout, "
            "content hashes, and execution provenance; no external signature"
        ),
    }


def run_tournament(
    repository: str | Path,
    output_directory: str | Path,
    *,
    max_workers: int = 8,
    full_suite: bool = True,
    plan: Mapping[str, Any] | None = None,
    command_runner: Callable[[Path, Sequence[str]], tuple[dict[str, Any], str]] = run_command_receipt,
) -> dict[str, Any]:
    root = Path(repository).resolve()
    run_dir = Path(output_directory).resolve()
    if run_dir.exists():
        raise TournamentError(f"output directory must not already exist: {run_dir}")
    if max_workers < 2 or max_workers > len(TOURNAMENT_ROLES):
        raise TournamentError(f"max_workers must be between 2 and {len(TOURNAMENT_ROLES)}")
    if not Path(__file__).resolve().is_relative_to((root / "src/hive_mind_os").resolve()):
        raise TournamentError("tournament runtime was not imported from the repository under test")
    plan_document = dict(plan or build_tournament_plan())
    waves = validate_tournament_plan(plan_document)
    run_dir.mkdir(parents=True)
    receipts_dir = run_dir / "receipts"
    transcripts_dir = run_dir / "transcripts"
    receipts_dir.mkdir()
    transcripts_dir.mkdir()
    _write_json(run_dir / "plan.json", plan_document)
    receipts: dict[str, dict[str, Any]] = {}
    event_path = run_dir / "events.jsonl"

    def record(node_id: str, value: dict[str, Any], transcript: str | None = None) -> None:
        receipts[node_id] = value
        _write_json(receipts_dir / f"{node_id}.json", value)
        if transcript is not None:
            (transcripts_dir / f"{node_id}.txt").write_bytes(transcript.encode("utf-8"))
        event = {
            "sequence": len(receipts),
            "node_id": node_id,
            "status": "completed",
            "receipt_digest": value.get("receipt_digest") or value.get("grade_digest") or value.get("feedback_digest") or value.get("inventory_digest") or value.get("report_digest"),
            "previous_event_digest": None,
        }
        previous = None
        if event_path.exists():
            previous_line = event_path.read_text(encoding="utf-8").splitlines()[-1]
            previous_event = _strict_json_value(previous_line, label="previous event")
            if not isinstance(previous_event, Mapping):
                raise TournamentError("previous event must contain a JSON object")
            previous = previous_event["event_digest"]
        event["previous_event_digest"] = previous
        event["event_digest"] = canonical_digest(event)
        with event_path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")

    def execute(node_id: str) -> tuple[dict[str, Any], str | None]:
        raw = next(item for item in plan_document["nodes"] if item["node_id"] == node_id)
        action = raw["action"]
        if action == "inventory":
            inventory = inventory_repository(root, exclude=run_dir)
            inventory.pop("inventory_digest")
            inventory["execution"] = {
                "runner_identity": f"{command_runner.__module__}:{getattr(command_runner, '__qualname__', command_runner.__name__)}",
                "trusted_builtin_runner": command_runner is run_command_receipt,
                "runtime_path": "src/hive_mind_os/agent_tournament.py",
                "runtime_sha256": _sha256_bytes(Path(__file__).read_bytes()),
            }
            inventory["inventory_digest"] = canonical_digest(inventory)
            return inventory, None
        if action == "grade-role":
            return grade_role(root, str(raw["role"]), command_runner)
        if action == "static-repository":
            return static_repository_gate(root, receipts["SCAN-REPOSITORY"]), None
        if action == "system-test":
            return _test_lane(
                root,
                str(raw["lane"]),
                SYSTEM_TEST_LANES[str(raw["lane"])],
                command_runner,
            )
        if action == "control-plane-audit":
            return control_plane_gate(root, command_runner)
        if action == "full-suite":
            return _full_suite(root, full_suite)
        if action == "cross-examine":
            return cross_examine(receipts, root, exclude=run_dir), None
        if action == "feedback":
            return feedback_contract(
                receipts[_role_node_id(str(raw["role"]))],
                receipts["CROSS-EXAMINE"],
                max_cycles=int(plan_document["feedback_policy"]["max_cycles"]),
            ), None
        if action == "championship":
            return championship(receipts, str(plan_document["plan_digest"])), None
        raise TournamentError(f"node {node_id} has unsupported action {action}")

    def execute_with_retries(
        node_id: str,
    ) -> tuple[dict[str, Any], str | None, list[dict[str, Any]]]:
        raw = next(item for item in plan_document["nodes"] if item["node_id"] == node_id)
        attempt_rows: list[dict[str, Any]] = []
        for attempt in range(1, int(raw["max_attempts"]) + 1):
            attempt_started_at = _now()
            started_monotonic = time.monotonic()
            try:
                value, transcript = execute(node_id)
                attempt_rows.append(
                    {
                        "attempt": attempt,
                        "outcome": "completed",
                        "receipt_status": value.get("status", "completed"),
                        "started_at": attempt_started_at,
                        "ended_at": _now(),
                        "duration_ms": round((time.monotonic() - started_monotonic) * 1000),
                    }
                )
                return value, transcript, attempt_rows
            except (OSError, TimeoutError, subprocess.SubprocessError) as error:
                attempt_rows.append(
                    {
                        "attempt": attempt,
                        "outcome": "infrastructure-exception",
                        "error": f"{type(error).__name__}: {error}",
                        "started_at": attempt_started_at,
                        "ended_at": _now(),
                        "duration_ms": round((time.monotonic() - started_monotonic) * 1000),
                    }
                )
            except Exception as error:
                attempt_rows.append(
                    {
                        "attempt": attempt,
                        "outcome": "contract-or-evidence-exception",
                        "error": f"{type(error).__name__}: {error}",
                        "started_at": attempt_started_at,
                        "ended_at": _now(),
                        "duration_ms": round((time.monotonic() - started_monotonic) * 1000),
                    }
                )
                failure: dict[str, Any] = {
                    "node_id": node_id,
                    "status": "contract-failed",
                    "critical": True,
                    "error": attempt_rows[-1]["error"],
                    "attempts_executed": len(attempt_rows),
                }
                failure["receipt_digest"] = canonical_digest(failure)
                return failure, None, attempt_rows
        failure: dict[str, Any] = {
            "node_id": node_id,
            "status": "infrastructure-failed",
            "critical": True,
            "error": attempt_rows[-1]["error"],
            "attempts_exhausted": len(attempt_rows),
        }
        failure["receipt_digest"] = canonical_digest(failure)
        return failure, None, attempt_rows

    for wave_number, wave in enumerate(waves, start=1):
        wave_workers = min(max_workers, len(wave))
        wave_record: dict[str, Any] = {
            "wave": wave_number,
            "nodes": list(wave),
            "parallel": len(wave) > 1 and wave_workers > 1,
            "workers_used": wave_workers,
            "status": "running",
            "attempts": {},
            "observed_peak_command_concurrency": 0,
        }
        wave_path = run_dir / "waves" / f"wave-{wave_number:02d}.json"
        _write_json(wave_path, wave_record)
        with ThreadPoolExecutor(max_workers=wave_workers) as pool:
            futures = {pool.submit(execute_with_retries, node_id): node_id for node_id in wave}
            completed_values: dict[
                str, tuple[dict[str, Any], str | None, list[dict[str, Any]]]
            ] = {}
            for future in as_completed(futures):
                node_id = futures[future]
                completed_values[node_id] = future.result()
        wave_record["status"] = "completed"
        wave_record["attempts"] = {
            node_id: completed_values[node_id][2] for node_id in wave
        }
        wave_record["observed_peak_concurrency"] = _observed_peak_concurrency(
            wave_record["attempts"]
        )
        command_attempts = {
            node_id: [
                {
                    "started_at": nested["started_at"],
                    "ended_at": nested["ended_at"],
                }
            ]
            for node_id in wave
            if isinstance(
                nested := completed_values[node_id][0].get("test_receipt")
                or completed_values[node_id][0].get("command_receipt"),
                Mapping,
            )
        }
        wave_record["observed_peak_command_concurrency"] = _observed_peak_concurrency(
            command_attempts
        )
        _write_json(wave_path, wave_record)
        failed_nodes: list[str] = []
        for node_id in wave:
            value, transcript, _attempts = completed_values[node_id]
            record(node_id, value, transcript)
            if value.get("status") in {"infrastructure-failed", "contract-failed"}:
                failed_nodes.append(node_id)
        if failed_nodes:
            incomplete: dict[str, Any] = {
                "schema_version": 1,
                "kind": "hive-mind-agent-readiness-incomplete-run",
                "status": "node-failed",
                "plan_digest": plan_document["plan_digest"],
                "failed_nodes": failed_nodes,
                "completed_nodes": list(receipts),
                "restart": "use a new create-only output directory",
            }
            incomplete["incomplete_digest"] = canonical_digest(incomplete)
            _write_json(run_dir / "incomplete.json", incomplete)
            _write_json(run_dir / "manifest.json", _manifest(run_dir))
            raise TournamentError(
                "node execution failed or infrastructure attempts exhausted for nodes: "
                + ", ".join(failed_nodes)
            )

    report = receipts["CHAMPIONSHIP"]
    _write_json(run_dir / "report.json", report)
    _write_markdown(run_dir / "report.md", report)
    _write_json(run_dir / "manifest.json", _manifest(run_dir))
    return verify_run_directory(run_dir, repository=root)


def _load_plan(path: str | None) -> Mapping[str, Any] | None:
    return None if path is None else _read_json(Path(path))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the parallel Hive Mind agent-readiness tournament")
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="write the canonical executable tournament DAG")
    plan.add_argument("--output", required=True)
    run = commands.add_parser("run", help="execute the DAG and write a new evidence bundle")
    run.add_argument("--repository", default=".")
    run.add_argument("--output-dir", required=True)
    run.add_argument("--plan")
    run.add_argument("--max-workers", type=int, default=8)
    run.add_argument("--skip-full-suite", action="store_true")
    verify = commands.add_parser("verify", help="verify every bound artifact in a completed run")
    verify.add_argument("--run-dir", required=True)
    verify.add_argument("--repository", default=".")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "plan":
            output = Path(args.output)
            if output.exists():
                raise TournamentError(f"output must not already exist: {output}")
            _write_json(output, build_tournament_plan())
            result = {"status": "planned", "path": str(output.resolve()), "plan_digest": _read_json(output)["plan_digest"]}
        elif args.command == "run":
            result = run_tournament(
                args.repository,
                args.output_dir,
                max_workers=args.max_workers,
                full_suite=not args.skip_full_suite,
                plan=_load_plan(args.plan),
            )
        else:
            result = verify_run_directory(args.run_dir, repository=args.repository)
    except (OSError, ValueError, TournamentError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
