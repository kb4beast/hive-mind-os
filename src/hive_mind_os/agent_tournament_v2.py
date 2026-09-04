"""Create-only, repository-wide v2 agent-readiness tournament.

Version two composes the hardened v1 command/evidence primitives with two new
surfaces: a real multi-fixture code-to-QA corpus and an externally authorized
challenger boundary.  It remains an offline structural tournament.  In
particular, an authority manifest alone cannot stand in for an evaluator-owned
holdout or candidate-bound surface receipts, so the challenger is retained as
``retest-required`` and is never materialized or promoted by this module.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sqlite3
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from uuid import UUID

from . import agent_tournament as v1
from .brain_kernel.artifacts import ArtifactStore
from .brain_kernel.canonical import canonical_bytes, canonical_digest
from .brain_kernel.challenger_runtime import ChallengerFinding, V2ChallengerRuntime
from .brain_kernel.contracts import normalize_portable_path
from .brain_kernel.dag_runtime import (
    ISOLATION_ASSURANCE,
    DagEvent,
    ExecutableDagRuntime,
    NodeReceipt,
    NodeStatus,
)
from .brain_kernel.evaluation_authority import (
    EvaluationAuthorityManifest,
    capture_repository_binding,
    load_evaluation_authority_manifest,
)
from .brain_kernel.evaluation_runtime import EvaluationRuntime
from .brain_kernel.promotion import PromotionAuthority
from .cortex.repository.code_qa_corpus import (
    PINNED_CORPUS_BUNDLE_DIGEST,
    CorpusRun,
    run_code_qa_corpus,
)
from .cortex.repository.specialist_handlers import (
    RepositorySpecialistHandlers,
    repository_candidate_digest,
    repository_specialist_plan,
)
from .models import Role
from .prompt_registry import PromptRegistry, generation_zero_prompt, prompt_digest
from .roles import ROLE_CONTRACTS

TOURNAMENT_ROLES = v1.TOURNAMENT_ROLES
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_RUNTIME_PATH = "src/hive_mind_os/agent_tournament_v2.py"
_FIXTURE_ROOT = "tests/fixtures/code_qa_v2"
_MAX_ARTIFACT_BYTES = 256 * 1024 * 1024
_MAX_BUNDLE_BYTES = 2 * 1024 * 1024 * 1024
_MAX_MANIFEST_ENTRIES = 100_000

_LEGACY_SYSTEM_NODES: Mapping[str, str] = {
    "SYSTEM-STATIC": "static",
    "SYSTEM-LIFECYCLE": "lifecycle",
    "SYSTEM-RESILIENCE": "resilience",
    "SYSTEM-EVOLUTION": "evolution",
    "SYSTEM-CONTROL-PLANE": "control-plane",
    "SYSTEM-CONTROL-PLANE-TESTS": "control-plane-tests",
    "SYSTEM-CONTROL-PLANE-DOCTOR": "control-plane-doctor",
    "SYSTEM-FULL-SUITE": "full-suite",
}
_STRICT_SYSTEM_NODES = (
    "SYSTEM-STATIC",
    "SYSTEM-LIFECYCLE",
    "SYSTEM-RESILIENCE",
    "SYSTEM-EVOLUTION",
    "SYSTEM-CONTROL-PLANE",
    "SYSTEM-CONTROL-PLANE-TESTS",
    "SYSTEM-CONTROL-PLANE-DOCTOR",
    "SYSTEM-NATIVE-DAG",
    "SYSTEM-CODE-QA-V2",
    "SYSTEM-FULL-SUITE",
)

_NATIVE_PAYLOAD_FIELDS: Mapping[str, frozenset[str]] = {
    "orchestrator": frozenset(
        {"role", "orchestration_plan_digest", "planned_work_ids", "effect_authority"}
    ),
    "explorer": frozenset(
        {
            "role",
            "tracked_file_count",
            "test_file_count",
            "tracked_files_receipt_digest",
            "trust_boundary",
            "sample_tests",
        }
    ),
    "architect": frozenset(
        {"role", "architecture_digest", "selected_option", "unknowns"}
    ),
    "builder": frozenset(
        {"role", "actions", "workspace_product", "workspace_product_digest"}
    ),
    "curator": frozenset(
        {
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
    ),
    "integrator": frozenset(
        {
            "role",
            "status",
            "compatibility_report_digest",
            "lineage_digest",
            "findings",
            "builder_remands",
            "curator_evidence_complete",
        }
    ),
    "steward": frozenset(
        {
            "role",
            "readiness",
            "report_digest",
            "surface_statuses",
            "observed_surfaces",
            "unobserved_surfaces",
            "limitation",
        }
    ),
    "optimizer": frozenset(
        {
            "role",
            "lesson_digest",
            "challenger_proposal_digest",
            "evidence_complete",
            "completeness_reasons",
            "recommendation",
            "promotion_effect",
        }
    ),
}


class TournamentV2Error(RuntimeError):
    """The v2 tournament cannot establish trustworthy evidence."""


CommandRunner = Callable[[Path, Sequence[str]], tuple[dict[str, Any], str]]
_BUILTIN_RECEIPT_RUNNER = v1.run_command_receipt
_BUILTIN_COMMAND_RUNNER: CommandRunner = _BUILTIN_RECEIPT_RUNNER
_BUILTIN_COMMAND_RUNNER_IDENTITY = v1._callable_identity(_BUILTIN_COMMAND_RUNNER)


@dataclass(frozen=True, slots=True)
class DagNode:
    node_id: str
    action: str
    dependencies: tuple[str, ...]
    parallel_safe: bool
    objective: str
    critical: bool = False
    role: str | None = None
    lane: str | None = None

    def document(self) -> dict[str, Any]:
        document = asdict(self)
        document["dependencies"] = list(self.dependencies)
        return document


def _role_node(role: str) -> str:
    return f"ROLE-{role.upper()}"


def _feedback_node(role: str) -> str:
    return f"FEEDBACK-{role.upper()}"


def _canonical_nodes() -> tuple[DagNode, ...]:
    roles = tuple(_role_node(role) for role in TOURNAMENT_ROLES)
    system_parallel = (
        "SYSTEM-STATIC",
        "SYSTEM-LIFECYCLE",
        "SYSTEM-RESILIENCE",
        "SYSTEM-EVOLUTION",
        "SYSTEM-CONTROL-PLANE",
        "SYSTEM-CONTROL-PLANE-TESTS",
        "SYSTEM-NATIVE-DAG",
        "SYSTEM-CODE-QA-V2",
    )
    nodes: list[DagNode] = [
        DagNode(
            "SCAN-REPOSITORY",
            "seal-repository",
            (),
            False,
            "Seal every Git-visible file plus exact HEAD, tree, and checkout state.",
            True,
        )
    ]
    for role in TOURNAMENT_ROLES:
        nodes.append(
            DagNode(
                _role_node(role),
                "grade-role",
                ("SCAN-REPOSITORY",),
                True,
                f"Grade {role} independently with source-bound focused tests.",
                True,
                role=role,
            )
        )
    for node_id, lane in (
        ("SYSTEM-STATIC", "static"),
        ("SYSTEM-LIFECYCLE", "lifecycle"),
        ("SYSTEM-RESILIENCE", "resilience"),
        ("SYSTEM-EVOLUTION", "evolution"),
        ("SYSTEM-CONTROL-PLANE", "control-plane"),
        ("SYSTEM-CONTROL-PLANE-TESTS", "control-plane-tests"),
        ("SYSTEM-NATIVE-DAG", "native-dag"),
        ("SYSTEM-CODE-QA-V2", "code-qa-v2"),
    ):
        nodes.append(
            DagNode(
                node_id,
                "system-gate",
                roles,
                True,
                {
                    "static": "Parse and compile the exact sealed repository.",
                    "lifecycle": "Exercise the native all-role lifecycle.",
                    "resilience": "Exercise recovery, no-cheating, and poisoning defenses.",
                    "evolution": "Exercise learning, evaluation, and promotion boundaries.",
                    "control-plane": "Run strict predecessor control-plane validation.",
                    "control-plane-tests": "Run the separately governed control-plane tests.",
                    "native-dag": (
                        "Execute all eight concrete repository specialists through the "
                        "dependency-ready typed DAG on an isolated exact source snapshot."
                    ),
                    "code-qa-v2": (
                        "Create code through authority-bound effects and separately run "
                        "public and sealed checks across three fixture shapes."
                    ),
                }[lane],
                True,
                lane=lane,
            )
        )
    nodes.extend(
        (
            DagNode(
                "SYSTEM-CONTROL-PLANE-DOCTOR",
                "system-gate",
                (*roles, "SYSTEM-CONTROL-PLANE-TESTS"),
                False,
                "Run the exact bootstrap doctor in its disposable isolated checkout.",
                True,
                lane="control-plane-doctor",
            ),
            DagNode(
                "CHALLENGER-G1",
                "challenger-boundary",
                (*roles, *system_parallel, "SYSTEM-CONTROL-PLANE-DOCTOR"),
                False,
                (
                    "Authenticate external evaluation authority and retain an owned G1 "
                    "proposal, or explicitly defer at the evaluator evidence boundary."
                ),
                False,
                lane="challenger-g1",
            ),
            DagNode(
                "SYSTEM-FULL-SUITE",
                "full-suite",
                (*system_parallel, "SYSTEM-CONTROL-PLANE-DOCTOR", "CHALLENGER-G1"),
                False,
                "Run the canonical repository CI gate; development skips cannot adopt.",
                True,
                lane="full-suite",
            ),
            DagNode(
                "CROSS-EXAMINE",
                "cross-examine",
                ("SYSTEM-FULL-SUITE",),
                False,
                "Attack every apparent pass and preserve fatal findings and dissent.",
                True,
            ),
        )
    )
    for role in TOURNAMENT_ROLES:
        nodes.append(
            DagNode(
                _feedback_node(role),
                "feedback",
                (_role_node(role), "CROSS-EXAMINE", "CHALLENGER-G1"),
                True,
                (
                    f"Challenge {role}, rethink from source evidence, and emit bounded "
                    "fresh-run re-entry without mutating its champion."
                ),
                False,
                role=role,
            )
        )
    nodes.append(
        DagNode(
            "CHAMPIONSHIP",
            "championship",
            tuple(_feedback_node(role) for role in TOURNAMENT_ROLES),
            False,
            "Issue a non-compensating system verdict without a superiority claim.",
            True,
        )
    )
    return tuple(nodes)


def _derive_waves(nodes: Sequence[Mapping[str, Any]]) -> tuple[tuple[str, ...], ...]:
    by_id = {str(node["node_id"]): node for node in nodes}
    if len(by_id) != len(nodes):
        raise TournamentV2Error("plan node ids must be unique")
    pending = set(by_id)
    completed: set[str] = set()
    waves: list[tuple[str, ...]] = []
    while pending:
        ready = tuple(
            node_id
            for node_id in by_id
            if node_id in pending
            and set(by_id[node_id]["dependencies"]).issubset(completed)
        )
        if not ready:
            raise TournamentV2Error("plan contains a cycle or missing dependency")
        waves.append(ready)
        completed.update(ready)
        pending.difference_update(ready)
    return tuple(waves)


def build_tournament_plan_v2() -> dict[str, Any]:
    nodes = [node.document() for node in _canonical_nodes()]
    waves = _derive_waves(nodes)
    document: dict[str, Any] = {
        "schema_version": 2,
        "kind": "hive-mind-agent-readiness-tournament-v2-plan",
        "executor": {
            "module": "hive_mind_os.agent_tournament_v2",
            "script": "scripts/run_agent_tournament_v2.py",
        },
        "policies": {
            "create_only_output": True,
            "fatal_gates_are_non_compensating": True,
            "default_runs_canonical_full_suite": True,
            "skip_full_suite_can_never_adopt": True,
            "authority_manifest_requires_caller_expected_digest": True,
            "authority_only_challenger_status": "retest-required",
            "challenger_promotion_authorized": False,
            "feedback_cycles": 3,
        },
        "nodes": nodes,
        "waves": [list(wave) for wave in waves],
    }
    document["plan_digest"] = canonical_digest(document)
    return document


def validate_tournament_plan_v2(
    document: Mapping[str, Any],
) -> tuple[tuple[str, ...], ...]:
    expected = build_tournament_plan_v2()
    if canonical_digest(document) != canonical_digest(expected) or document != expected:
        raise TournamentV2Error("v2 plan differs from the code-owned canonical DAG")
    supplied = document.get("plan_digest")
    material = dict(document)
    material.pop("plan_digest", None)
    if supplied != canonical_digest(material):
        raise TournamentV2Error("v2 plan digest is invalid")
    nodes = document.get("nodes")
    if not isinstance(nodes, list):
        raise TournamentV2Error("v2 plan nodes are invalid")
    waves = _derive_waves(nodes)
    if document.get("waves") != [list(wave) for wave in waves]:
        raise TournamentV2Error("v2 plan waves are not derivable")
    for node in nodes:
        if not isinstance(node, Mapping) or set(node) != {
            "node_id",
            "action",
            "dependencies",
            "parallel_safe",
            "objective",
            "critical",
            "role",
            "lane",
        }:
            raise TournamentV2Error("v2 plan contains a malformed node")
        dependencies = node["dependencies"]
        if not isinstance(dependencies, list):
            # ``asdict`` preserves tuples.  JSON loading changes them to lists;
            # normalize both representations through the canonical expected plan.
            if not isinstance(dependencies, tuple):
                raise TournamentV2Error("v2 node dependencies are invalid")
    return waves


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _utc_moment(value: object, *, label: str) -> datetime:
    if not isinstance(value, str):
        raise TournamentV2Error(f"{label} is not a UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise TournamentV2Error(f"{label} is not a UTC timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(None):
        raise TournamentV2Error(f"{label} is not a UTC timestamp")
    return parsed.astimezone(UTC)


def _sha256_file(path: Path) -> str:
    return v1._sha256_file(path)


def _strict_json(path: Path) -> Mapping[str, Any]:
    return v1._read_json(path)


def _reject_json_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _write_json_create(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    try:
        with path.open("xb") as stream:
            stream.write(payload)
    except FileExistsError as error:
        raise TournamentV2Error(
            f"create-only artifact already exists: {path}"
        ) from error


def _write_text_create(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(value)
    except FileExistsError as error:
        raise TournamentV2Error(
            f"create-only artifact already exists: {path}"
        ) from error


def _receipt_digest(value: Mapping[str, Any]) -> str:
    for field in (
        "receipt_digest",
        "grade_digest",
        "feedback_digest",
        "report_digest",
    ):
        digest = value.get(field)
        if isinstance(digest, str) and _DIGEST.fullmatch(digest):
            return digest
    raise TournamentV2Error("node receipt lacks a canonical digest")


def _self_digest(value: Mapping[str, Any], field: str) -> None:
    material = dict(value)
    supplied = material.pop(field, None)
    if supplied != canonical_digest(material):
        raise TournamentV2Error(f"{field} is invalid")


def _require_disjoint_roots(repository: Path, run_root: Path, *, label: str) -> None:
    if v1._paths_overlap(repository, run_root):
        raise TournamentV2Error(f"{label} must be outside the selected repository")


def _scan_receipt(
    repository: Path,
    inventory: Mapping[str, Any],
    *,
    command_runner: CommandRunner,
) -> dict[str, Any]:
    binding = capture_repository_binding(repository)
    document: dict[str, Any] = {
        "schema_version": 2,
        "kind": "hive-mind-agent-readiness-repository-seal-v2",
        "inventory": dict(inventory),
        "repository_binding": asdict(binding),
        "execution": {
            "runtime_path": _RUNTIME_PATH,
            "runtime_sha256": _sha256_file(Path(__file__).resolve()),
            "command_runner_identity": (v1._callable_identity(command_runner)),
            "trusted_builtin_command_runner": (
                command_runner is _BUILTIN_COMMAND_RUNNER
                and v1.run_command_receipt is _BUILTIN_COMMAND_RUNNER
            ),
        },
    }
    document["receipt_digest"] = canonical_digest(document)
    return document


def _generic_failure(node_id: str, error: BaseException) -> dict[str, Any]:
    document: dict[str, Any] = {
        "node_id": node_id,
        "status": "contract-failed",
        "critical": True,
        "error_class": type(error).__name__,
        "error": str(error),
    }
    document["receipt_digest"] = canonical_digest(document)
    return document


def _code_qa_summary(result: CorpusRun, run_root: Path) -> dict[str, Any]:
    corpus_path = run_root / "code-qa" / "corpus-run.json"
    tasks: list[dict[str, Any]] = []
    retained_losses = 0
    for task in result.task_runs:
        losses = sum(attempt.disposition != "succeeded" for attempt in task.attempts)
        retained_losses += losses
        final = task.attempts[-1]
        tasks.append(
            {
                "task_id": task.task_id,
                "shape": task.shape,
                "status": task.status,
                "baseline_public_passed": task.baseline.public_outcome.passed,
                "attempt_count": len(task.attempts),
                "retained_losing_attempts": losses,
                "winner_candidate_digest": (
                    final.evidence.candidate_digest
                    if final.evidence is not None and final.disposition == "succeeded"
                    else None
                ),
                "winner_public_passed": final.public_outcome.passed,
                "winner_hidden_passed": final.hidden_outcome.passed,
                "result_digest": task.result_digest,
            }
        )
    qualified = (
        result.status == "succeeded"
        and result.scope == "complete-bounded-corpus"
        and result.bundle_digest == PINNED_CORPUS_BUNDLE_DIGEST
        and result.pin_mode == "caller-pinned-same-trust-local-development"
        and result.independent_evaluator is False
        and result.adaptive_intelligence is False
        and len(tasks) >= 3
        and len({task["shape"] for task in tasks}) == len(tasks)
        and all(
            task["status"] == "succeeded"
            and task["baseline_public_passed"] is False
            and task["attempt_count"] >= 2
            and task["retained_losing_attempts"] >= 1
            and task["winner_public_passed"] is True
            and task["winner_hidden_passed"] is True
            for task in tasks
        )
    )
    document: dict[str, Any] = {
        "lane": "code-qa-v2",
        "status": "passed" if qualified else "failed",
        "critical": not qualified,
        "fixture_root": _FIXTURE_ROOT,
        "corpus_run_path": "code-qa/corpus-run.json",
        "corpus_run_sha256": _sha256_file(corpus_path),
        "corpus_digest": result.corpus_digest,
        "bundle_digest": result.bundle_digest,
        "pin_mode": result.pin_mode,
        "scope": result.scope,
        "expected_task_ids": list(result.expected_task_ids),
        "selected_task_ids": list(result.selected_task_ids),
        "task_contract_digests": list(result.task_contract_digests),
        "evaluator_id": result.evaluator_id,
        "qualification": result.qualification,
        "operationally_qualified": result.operationally_qualified,
        "independent_evaluator": result.independent_evaluator,
        "adaptive_intelligence": result.adaptive_intelligence,
        "trust_model": result.trust_model,
        "limitations": list(result.limitations),
        "task_count": len(tasks),
        "retained_losing_attempt_count": retained_losses,
        "tasks": tasks,
    }
    document["receipt_digest"] = canonical_digest(document)
    return document


def _run_code_qa(repository: Path, run_root: Path) -> dict[str, Any]:
    result = run_code_qa_corpus(
        repository / _FIXTURE_ROOT,
        run_root / "code-qa",
        expected_bundle_digest=PINNED_CORPUS_BUNDLE_DIGEST,
    )
    return _code_qa_summary(result, run_root)


_NATIVE_DAG_TEST_MODULES = (
    "tests.test_brain_kernel_dag_runtime",
    "tests.test_brain_kernel_specialist_handlers",
    "tests.test_repository_specialist_handlers",
)


def _repository_file_set_digest(inventory: Mapping[str, Any]) -> str:
    return canonical_digest({"files": inventory.get("files")})


def _validate_native_payload(
    role: str,
    payload: Mapping[str, Any],
    repository_binding: Mapping[str, Any],
) -> None:
    """Validate the bounded semantic contract emitted by one native role."""

    if set(payload) != _NATIVE_PAYLOAD_FIELDS[role] or payload.get("role") != role:
        raise TournamentV2Error(f"native {role} artifact fields are invalid")
    for key, value in payload.items():
        if key.endswith("_digest") and (
            not isinstance(value, str) or _DIGEST.fullmatch(value) is None
        ):
            raise TournamentV2Error(f"native {role} artifact digest is invalid")
    if role == "orchestrator" and (
        payload.get("planned_work_ids") != ["WORK-specialist-observation"]
        or payload.get("effect_authority") != "none; planning only"
    ):
        raise TournamentV2Error("native Orchestrator outcome is not bounded")
    if role == "explorer" and (
        type(payload.get("tracked_file_count")) is not int
        or int(payload["tracked_file_count"]) < 1
        or type(payload.get("test_file_count")) is not int
        or int(payload["test_file_count"]) < 1
        or payload.get("trust_boundary") != "untrusted-command-output"
        or not isinstance(payload.get("sample_tests"), list)
        or len(payload["sample_tests"]) > 20
        or any(not isinstance(item, str) for item in payload["sample_tests"])
    ):
        raise TournamentV2Error("native Explorer outcome is invalid")
    if role == "architect" and (
        payload.get("selected_option") != "dependency-ready-dag"
        or not isinstance(payload.get("unknowns"), list)
    ):
        raise TournamentV2Error("native Architect outcome is invalid")
    if role == "builder":
        actions = payload.get("actions")
        if (
            payload.get("workspace_product") != "candidate/builder-output.json"
            or not isinstance(actions, list)
            or len(actions) != 2
            or [row.get("action_id") for row in actions if isinstance(row, Mapping)]
            != ["write-specialist-output", "check-specialist-output"]
            or any(
                not isinstance(row, Mapping)
                or set(row)
                != {"action_id", "status", "effect_receipt_digest", "output_digest"}
                or row.get("status") != "SUCCEEDED"
                or any(
                    not isinstance(row.get(key), str)
                    or _DIGEST.fullmatch(str(row[key])) is None
                    for key in ("effect_receipt_digest", "output_digest")
                )
                for row in actions
            )
        ):
            raise TournamentV2Error("native Builder outcome is invalid")
    if role == "curator":
        checks = payload.get("check_results")
        expected_checks = [
            ["builder-artifact-and-product", True],
            ["repository-test-presence", True],
            ["repository-nonrecursive-smoke", True],
        ]
        bound_checks = (
            payload.get("builder_validation"),
            payload.get("test_presence"),
            payload.get("smoke_test"),
        )
        if (
            payload.get("candidate_commit") != repository_binding.get("head_commit")
            or payload.get("candidate_tree") != repository_binding.get("tree_oid")
            or payload.get("verdict") != "adopt"
            or checks != expected_checks
            or any(
                not isinstance(item, Mapping) or item.get("passed") is not True
                for item in bound_checks
            )
        ):
            raise TournamentV2Error("native Curator outcome is invalid")
    if role == "integrator" and (
        payload.get("status") != "compatible"
        or payload.get("curator_evidence_complete") is not True
        or payload.get("builder_remands") != []
        or not isinstance(payload.get("findings"), list)
    ):
        raise TournamentV2Error("native Integrator outcome is invalid")
    if role == "steward":
        observed = ["receipts", "snapshots", "workspaces"]
        unobserved = ["event_chains", "leases", "providers", "queues"]
        statuses = payload.get("surface_statuses")
        if (
            payload.get("readiness") != "repair_required"
            or payload.get("observed_surfaces") != observed
            or payload.get("unobserved_surfaces") != unobserved
            or not isinstance(statuses, Mapping)
            or set(statuses) != set(observed + unobserved)
            or any(statuses.get(name) != "healthy" for name in observed)
            or any(statuses.get(name) != "degraded" for name in unobserved)
            or not isinstance(payload.get("limitation"), str)
        ):
            raise TournamentV2Error(
                "native Steward bounded-readiness outcome is invalid"
            )
    if role == "optimizer" and (
        payload.get("evidence_complete") is not False
        or payload.get("completeness_reasons")
        != ["operational-surfaces-are-unobserved-or-unhealthy"]
        or payload.get("recommendation") != "defer"
        or payload.get("promotion_effect")
        != "none; independent court review is still required"
    ):
        raise TournamentV2Error("native Optimizer bounded recommendation is invalid")


def _native_semantic_outcomes(
    payloads: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Project the composition-critical outcomes without upgrading their burden."""

    curator = payloads.get("curator", {})
    integrator = payloads.get("integrator", {})
    steward = payloads.get("steward", {})
    optimizer = payloads.get("optimizer", {})
    return {
        "curator": {"verdict": curator.get("verdict")},
        "integrator": {
            "status": integrator.get("status"),
            "curator_evidence_complete": integrator.get("curator_evidence_complete"),
            "builder_remands": integrator.get("builder_remands"),
        },
        "steward": {
            "readiness": steward.get("readiness"),
            "observed_surfaces": steward.get("observed_surfaces"),
            "unobserved_surfaces": steward.get("unobserved_surfaces"),
        },
        "optimizer": {
            "recommendation": optimizer.get("recommendation"),
            "evidence_complete": optimizer.get("evidence_complete"),
            "completeness_reasons": optimizer.get("completeness_reasons"),
        },
    }


def _run_native_dag(
    repository: Path,
    run_root: Path,
    scan: Mapping[str, Any],
    command_runner: CommandRunner,
) -> tuple[dict[str, Any], str]:
    """Run the concrete eight-role DAG against a disposable exact Git clone."""

    clean_state = canonical_digest({"status": [], "diff": ""})
    if scan["repository_binding"]["state_digest"] != clean_state:
        raise TournamentV2Error(
            "native specialist trial requires a clean exact source snapshot"
        )
    inventory = scan["inventory"]
    authority_roots = v1._source_authority_roots(repository, inventory)
    temporary_parent = v1._validated_ambient_temp_root(authority_roots)
    temporary_root = Path(
        tempfile.mkdtemp(prefix="hnd-v2-", dir=temporary_parent)
    ).resolve()
    temporary_identity = v1._owned_cleanup_identity(temporary_root)
    snapshot = temporary_root / "s"
    snapshot_before: dict[str, Any] | None = None
    snapshot_after: dict[str, Any] | None = None
    snapshot_inventory_digest: str | None = None
    snapshot_line_ending_mode: str | None = None
    result: Any = None
    native_root = run_root / "native-dag"
    workspace_cleanup_completed = False
    try:
        clone = v1._git(
            repository,
            "clone",
            "--quiet",
            "--no-hardlinks",
            "--no-checkout",
            str(repository),
            str(snapshot),
        )
        if clone.returncode != 0:
            raise TournamentV2Error("Git could not create the isolated native snapshot")
        checkout = v1._git(
            snapshot,
            "-c",
            "core.autocrlf=false",
            "checkout",
            "--quiet",
            "--detach",
            str(scan["repository_binding"]["head_commit"]),
        )
        if checkout.returncode != 0:
            raise TournamentV2Error("Git could not detach the isolated native snapshot")
        # Git's index can describe the same tree through platform-specific line
        # endings.  Reuse v1's hardened copier so the executable snapshot binds
        # the exact SCAN bytes as well as HEAD and tree identity.
        v1._materialize_inventory(repository, snapshot, inventory)
        for mode in ("false", "true", "input"):
            configuration = v1._git(
                snapshot, "config", "--local", "core.autocrlf", mode
            )
            semantic_diff = v1._git(snapshot, "diff", "--quiet", "--no-ext-diff")
            if configuration.returncode == semantic_diff.returncode == 0:
                snapshot_line_ending_mode = mode
                break
        if snapshot_line_ending_mode is None:
            raise TournamentV2Error(
                "exact-byte snapshot cannot reproduce the sealed clean Git state"
            )
        # Refresh only index stat/cache metadata.  Fail closed unless the index
        # still names the exact committed tree and the worktree then reports
        # clean; no candidate content is staged or rewritten.
        refreshed = v1._git(snapshot, "add", "--all")
        staged = v1._git(snapshot, "diff", "--cached", "--quiet")
        status = v1._git(
            snapshot,
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
        )
        if (
            refreshed.returncode != 0
            or staged.returncode != 0
            or status.returncode != 0
            or status.stdout
        ):
            raise TournamentV2Error(
                "exact-byte snapshot does not preserve the committed index/tree"
            )
        snapshot_before = asdict(capture_repository_binding(snapshot))
        if (
            snapshot_before["head_commit"] != scan["repository_binding"]["head_commit"]
            or snapshot_before["tree_oid"] != scan["repository_binding"]["tree_oid"]
            or snapshot_before["state_digest"] != clean_state
        ):
            raise TournamentV2Error("isolated native snapshot differs from source seal")
        snapshot_inventory = v1.inventory_repository(snapshot)
        snapshot_inventory_digest = _repository_file_set_digest(snapshot_inventory)
        if snapshot_inventory_digest != _repository_file_set_digest(inventory):
            raise TournamentV2Error(
                "isolated native snapshot file set differs from seal"
            )

        plan = repository_specialist_plan(plan_id="agent-readiness-tournament-v2")
        candidate_digest = repository_candidate_digest(snapshot, plan.digest)
        # Keep the disposable workspace path short enough for repositories with
        # long tracked names on Windows.  Only the content-addressed evidence
        # store is durable; workspaces remain under the owned temporary root.
        artifact_store = ArtifactStore(native_root / "evidence")
        runtime = ExecutableDagRuntime(
            temporary_root / "r",
            candidate_digest=candidate_digest,
            artifact_store=artifact_store,
            max_concurrency=len(TOURNAMENT_ROLES),
        )
        native_handlers = RepositorySpecialistHandlers(snapshot)
        start_barrier = threading.Barrier(2, timeout=30)
        overlap_lock = threading.Lock()
        overlap_trace: list[dict[str, Any]] = []
        handlers = {
            role: native_handlers.handler_for(role) for role in TOURNAMENT_ROLES
        }
        for concurrent_role in ("integrator", "steward"):
            native_handler = handlers[concurrent_role]

            def overlap_handler(
                context: Any,
                *,
                handler: Callable[[Any], Any] = native_handler,
                role: str = concurrent_role,
            ) -> Any:
                with overlap_lock:
                    overlap_trace.append(
                        {
                            "sequence": len(overlap_trace) + 1,
                            "role": role,
                            "event": "arrived",
                            "recorded_at": _now(),
                        }
                    )
                start_barrier.wait()
                with overlap_lock:
                    overlap_trace.append(
                        {
                            "sequence": len(overlap_trace) + 1,
                            "role": role,
                            "event": "released",
                            "recorded_at": _now(),
                        }
                    )
                return handler(context)

            handlers[concurrent_role] = overlap_handler
        result = asyncio.run(runtime.run(plan, handlers))
        snapshot_after = asdict(capture_repository_binding(snapshot))
        if snapshot_after != snapshot_before:
            raise TournamentV2Error(
                "native specialists mutated the isolated source snapshot"
            )
        workspaces = temporary_root / "r" / "workspaces"
        workspace_identity = v1._owned_cleanup_identity(workspaces)
        v1._remove_disposable_tree(
            workspaces,
            expected_identity=workspace_identity,
        )
        workspace_cleanup_completed = not os.path.lexists(workspaces)
        if not workspace_cleanup_completed:
            raise TournamentV2Error("native specialist workspaces survived cleanup")
    finally:
        v1._remove_disposable_tree(
            temporary_root,
            expected_identity=temporary_identity,
        )
    snapshot_cleanup_completed = not os.path.lexists(temporary_root)
    if not snapshot_cleanup_completed:
        raise TournamentV2Error("isolated native snapshot survived cleanup")
    if result is None or snapshot_before is None or snapshot_after is None:
        raise TournamentV2Error("native specialist trial produced no result")

    test_receipt, transcript = command_runner(
        repository,
        v1._unittest_command(_NATIVE_DAG_TEST_MODULES),
    )
    plan = repository_specialist_plan(plan_id="agent-readiness-tournament-v2")
    by_role = {receipt.role: receipt for receipt in result.receipts}
    integrator = next(node for node in plan.nodes if node.role == "integrator")
    steward = next(node for node in plan.nodes if node.role == "steward")
    overlap_eligible = (
        integrator.dependencies == steward.dependencies == ("05-curator",)
        and integrator.node_id not in steward.dependencies
        and steward.node_id not in integrator.dependencies
    )
    exact_native = (
        set(by_role) == set(TOURNAMENT_ROLES)
        and len({receipt.executor_id for receipt in result.receipts}) == 8
        and all(
            receipt.status is NodeStatus.SUCCEEDED
            and receipt.native_evidence
            and receipt.invoked_symbol
            == next(node.native_symbol for node in plan.nodes if node.role == role)
            for role, receipt in by_role.items()
        )
    )
    qualified = (
        exact_native
        and len(result.receipts) == len(result.events) == 8
        and overlap_eligible
        and result.max_observed_parallelism >= 2
        and snapshot_before == snapshot_after
        and workspace_cleanup_completed
        and snapshot_cleanup_completed
        and test_receipt.get("status") == "passed"
        and bool(test_receipt.get("tests_run"))
    )
    node_receipts = []
    native_payloads: dict[str, Mapping[str, Any]] = {}
    for receipt in result.receipts:
        row = receipt.to_document()
        row["receipt_digest"] = receipt.receipt_digest
        node_receipts.append(row)
        if receipt.artifact_digest is not None:
            stored = artifact_store.read(receipt.artifact_digest)
            try:
                payload = json.loads(
                    stored.content.decode("utf-8"),
                    object_pairs_hook=v1._reject_duplicate_object_pairs,
                    parse_constant=_reject_json_constant,
                )
            except (UnicodeError, json.JSONDecodeError, ValueError) as error:
                raise TournamentV2Error("native payload is not strict JSON") from error
            if (
                not isinstance(payload, Mapping)
                or canonical_bytes(payload) != stored.content
            ):
                raise TournamentV2Error("native payload is not canonical JSON")
            _validate_native_payload(receipt.role, payload, scan["repository_binding"])
            native_payloads[receipt.role] = payload
    document: dict[str, Any] = {
        "lane": "native-dag",
        "status": "passed" if qualified else "failed",
        "critical": not qualified,
        "plan": plan.to_document(),
        "plan_digest": plan.digest,
        "candidate_digest": result.candidate_digest,
        "node_receipts": node_receipts,
        "events": [asdict(event) for event in result.events],
        "logical_digest": result.logical_digest,
        "max_observed_parallelism": result.max_observed_parallelism,
        "ready_set_overlap": {
            "nodes": [integrator.node_id, steward.node_id],
            "shared_dependencies": list(integrator.dependencies),
            "eligible": overlap_eligible,
            "observed": overlap_eligible and result.max_observed_parallelism >= 2,
            "coordination": "two-party-start-barrier-before-native-handler",
            "events": overlap_trace,
            "assurance": "generation-time local observation; offline verifier checks its internal ordering",
        },
        "native_roles": sorted(by_role),
        "native_symbols": {
            role: by_role[role].invoked_symbol for role in sorted(by_role)
        },
        "executor_ids": {role: by_role[role].executor_id for role in sorted(by_role)},
        "semantic_outcomes": _native_semantic_outcomes(native_payloads),
        "snapshot": {
            "temporary_path": str(temporary_root),
            "before": snapshot_before,
            "after": snapshot_after,
            "file_set_digest": snapshot_inventory_digest,
            "git_line_ending_mode": snapshot_line_ending_mode,
            "cleanup_completed": snapshot_cleanup_completed,
        },
        "artifact_store_root": "native-dag/evidence",
        "workspace_cleanup_completed": workspace_cleanup_completed,
        "test_modules": list(_NATIVE_DAG_TEST_MODULES),
        "test_receipt": test_receipt,
        "operationally_qualified": False,
        "isolation_assurance": ISOLATION_ASSURANCE,
        "limitations": [
            "native handlers are deterministic local implementations, not live providers",
            "the in-process boundary is cooperative and is not an OS sandbox",
            "the trial uses the committed clean snapshot and performs no production effect",
            "offline verification checks native artifacts and receipts but does not re-execute the eight handlers",
        ],
    }
    document["receipt_digest"] = canonical_digest(document)
    return document, transcript


def _authority_challenger(
    repository: Path,
    run_root: Path,
    receipts: Mapping[str, Mapping[str, Any]],
    *,
    authority_path: Path | None,
    authority_digest: str | None,
) -> dict[str, Any]:
    if authority_path is None and authority_digest is None:
        document: dict[str, Any] = {
            "lane": "challenger-g1",
            "status": "deferred",
            "critical": False,
            "authority_supplied": False,
            "disposition": "defer",
            "reason": (
                "no caller-authenticated external evaluation authority was supplied"
            ),
            "promotion_authorized": False,
            "operationally_qualified": False,
        }
        document["receipt_digest"] = canonical_digest(document)
        return document
    if authority_path is None or authority_digest is None:
        raise TournamentV2Error(
            "challenger mode requires both authority manifest path and expected digest"
        )
    if _DIGEST.fullmatch(authority_digest) is None:
        raise TournamentV2Error("authority expected digest is malformed")

    resolved_authority = authority_path.resolve(strict=True)
    if v1._has_link_like_component(Path(resolved_authority.anchor), resolved_authority):
        raise TournamentV2Error("evaluation authority path contains a link or junction")
    if resolved_authority == run_root or resolved_authority.is_relative_to(run_root):
        raise TournamentV2Error(
            "evaluation authority must be external to the run bundle"
        )
    if resolved_authority == repository or resolved_authority.is_relative_to(
        repository
    ):
        raise TournamentV2Error(
            "evaluation authority must be external to the repository"
        )
    scan = receipts.get("SCAN-REPOSITORY")
    inventory = scan.get("inventory") if isinstance(scan, Mapping) else None
    if not isinstance(inventory, Mapping):
        raise TournamentV2Error(
            "evaluation authority externality requires the sealed repository inventory"
        )
    resolved_authority = v1._validate_path_outside_authority(
        resolved_authority,
        v1._source_authority_roots(repository, inventory),
        label="evaluation authority manifest",
    )
    challenger_root = run_root / "challenger"
    challenger_root.mkdir()
    authenticated_at = _now()
    registry_root = challenger_root / "registry"
    manifest = load_evaluation_authority_manifest(
        resolved_authority,
        expected_digest=authority_digest,
        repository_root=repository,
        candidate_root=registry_root,
        run_root=challenger_root,
        as_of=authenticated_at,
    )

    prompt_root = challenger_root / "generation-zero"
    prompt_root.mkdir()
    for role in Role:
        _write_text_create(
            prompt_root / f"{role.value}.txt",
            generation_zero_prompt(ROLE_CONTRACTS[role]),
        )
    registry = PromptRegistry(registry_root)
    pointer_before: bytes | None = None
    try:
        champions = registry.bootstrap(prompt_root)
        if champions != manifest.champions:
            raise TournamentV2Error(
                "authority role champions do not match generation-zero registry"
            )
        pointer_before = registry.pointer_path.read_bytes()
        runtime = V2ChallengerRuntime(
            manifest=manifest,
            repository_root=repository,
            run_root=challenger_root,
            registry=registry,
            artifact_store=ArtifactStore(challenger_root / "artifact-store"),
            promotion_authority=PromotionAuthority(registry),
            evaluation_runtime=EvaluationRuntime(),
            now=lambda: authenticated_at,
        )
        grades = [
            receipts[_role_node(role)]
            for role in TOURNAMENT_ROLES
            if receipts[_role_node(role)].get("role") == role
        ]
        if len(grades) != len(TOURNAMENT_ROLES):
            raise TournamentV2Error(
                "challenger proposal requires all eight role grades"
            )
        selected = min(
            grades,
            key=lambda item: (
                int(item.get("score", 0)),
                TOURNAMENT_ROLES.index(str(item["role"])),
            ),
        )
        role = str(selected["role"])
        evidence_refs = (
            f"role-grade:{selected['grade_digest']}",
            f"code-qa:{receipts['SYSTEM-CODE-QA-V2']['receipt_digest']}",
        )
        finding = ChallengerFinding(
            finding_id=f"finding:tournament-v2:{role}",
            role=role,
            source_episode_id=(
                "episode:tournament-v2:"
                + str(receipts["SCAN-REPOSITORY"]["receipt_digest"])[7:23]
            ),
            summary=f"{role} remains structurally graded but not operationally qualified",
            error_class="structural_evidence_only",
            proposed_change=(
                "require evaluator-owned held-out, PIT, adversarial, and comparator evidence"
            ),
            falsifier=(
                "the candidate fails any sealed hard guardrail or cannot beat pinned comparators"
            ),
            evidence_refs=evidence_refs,
            owner_id=manifest.identities.proposer_id,
            expires_at=manifest.expires_at,
        )
        proposal = runtime.propose(finding)
        pointer_after = registry.pointer_path.read_bytes()
        if pointer_before != pointer_after:
            raise TournamentV2Error("challenger proposal mutated the champion pointer")
        repository_after = capture_repository_binding(repository)
        binding = receipts["SCAN-REPOSITORY"]["repository_binding"]
        if asdict(repository_after) != binding:
            raise TournamentV2Error("challenger proposal changed the source checkout")
        retained = [
            {
                "path": path.relative_to(run_root).as_posix(),
                "sha256": _sha256_file(path),
            }
            for path in sorted(
                (challenger_root / "challenger-authority" / "proposal").glob("*.json")
            )
        ]
        if len(retained) != 1:
            raise TournamentV2Error(
                "challenger runtime did not retain exactly one proposal"
            )
        document = {
            "lane": "challenger-g1",
            "status": "retest-required",
            "critical": False,
            "authority_supplied": True,
            "authority_manifest_path": str(resolved_authority),
            "authority_manifest_sha256": _sha256_file(resolved_authority),
            "authority_manifest_digest": manifest.manifest_digest,
            "authenticated_at": authenticated_at,
            "repository_head": manifest.repository_head,
            "repository_tree": manifest.repository_tree,
            "selected_role": role,
            "finding": asdict(finding),
            "proposal_digest": proposal.proposal_digest,
            "hypothesis_id": proposal.hypothesis.hypothesis_id,
            "generation": proposal.hypothesis.generation,
            "parent_champion_digest": proposal.hypothesis.parent_champion_digest,
            "candidate_materialized": False,
            "evaluation_started": False,
            "disposition": "defer",
            "missing_evidence_obligations": [
                "evaluator-owned SealedHoldout with an intact pre-build prediction seal",
                "ArtifactStore-backed BoundSurfaceEvidence for held-out, PIT, adversarial, and pinned-comparator surfaces",
                "independent qualification receipts and issuer authority",
                "a genuine RETEST or DEFER outcome before generation-2 re-entry",
            ],
            "reentry_api": (
                "V2ChallengerRuntime.seal_evaluation -> materialize -> evaluate -> reenter"
            ),
            "retained_proposal_records": retained,
            "champion_pointer_unchanged": True,
            "promotion_authorized": False,
            "operationally_qualified": False,
            "qualification": (
                "authority authenticated and G1 proposal retained; no holdout, surface, "
                "provider, production, or superiority qualification"
            ),
        }
        document["receipt_digest"] = canonical_digest(document)
        return document
    finally:
        registry.close()


def _cross_examine_v2(
    repository: Path,
    receipts: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    opening = receipts["SCAN-REPOSITORY"]
    current_inventory = v1.inventory_repository(repository)
    current_binding = asdict(capture_repository_binding(repository))
    source_drift = (
        canonical_digest(current_inventory) != canonical_digest(opening["inventory"])
        or current_binding != opening["repository_binding"]
    )
    fatal: set[str] = set()
    gaps: set[str] = {
        "court identities are declared labels rather than authenticated independent principals",
        "passing deterministic checks does not establish live-provider quality or customer value",
        "the tournament is offline and does not qualify production deployment or hostile-code isolation",
        "no equal-budget multi-comparator superiority benchmark is executed by this runner",
    }
    execution = opening.get("execution")
    if (
        not isinstance(execution, Mapping)
        or execution.get("trusted_builtin_command_runner") is not True
    ):
        fatal.add(
            "SCAN-REPOSITORY: injected command runner is test-only and cannot support an authoritative verdict"
        )
    for role in TOURNAMENT_ROLES:
        grade = receipts[_role_node(role)]
        if grade.get("status") == "contract-failed":
            fatal.add(f"{role}: role node contract-failed")
            continue
        fatal.update(f"{role}: {item}" for item in grade.get("fatal_findings", ()))
        command = grade.get("test_receipt")
        if not isinstance(command, Mapping) or command.get("status") != "passed":
            fatal.add(f"{role}: focused role tests did not pass")
        court = grade.get("court")
        disposition = court.get("disposition") if isinstance(court, Mapping) else None
        if disposition not in {"adopt", "adapt"}:
            fatal.add(f"{role}: independent disposition is {disposition!s}")
        gaps.update(f"{role}: {item}" for item in grade.get("development_findings", ()))
        if grade.get("operationally_qualified") is not True:
            gaps.add(f"{role}: operational qualification remains unproven")
    for node_id in _STRICT_SYSTEM_NODES:
        receipt = receipts[node_id]
        status = receipt.get("status")
        if status == "deferred" and node_id == "SYSTEM-FULL-SUITE":
            gaps.add("canonical full suite was explicitly deferred by development mode")
        elif status != "passed":
            fatal.add(f"{node_id}: {status}")
    code_qa = receipts["SYSTEM-CODE-QA-V2"]
    gaps.update(str(item) for item in code_qa.get("limitations", ()))
    native_dag = receipts["SYSTEM-NATIVE-DAG"]
    gaps.update(str(item) for item in native_dag.get("limitations", ()))
    native_outcomes = native_dag.get("semantic_outcomes")
    if isinstance(native_outcomes, Mapping):
        steward = native_outcomes.get("steward")
        if isinstance(steward, Mapping) and (
            steward.get("readiness") != "ready"
            or bool(steward.get("unobserved_surfaces"))
        ):
            gaps.add(
                "native Steward requires repair because operational surfaces remain unobserved"
            )
        optimizer = native_outcomes.get("optimizer")
        if isinstance(optimizer, Mapping) and (
            optimizer.get("recommendation") != "promote"
            or optimizer.get("evidence_complete") is not True
        ):
            gaps.add("native Optimizer defers promotion because evidence is incomplete")
    challenger = receipts["CHALLENGER-G1"]
    if challenger.get("status") == "contract-failed":
        fatal.add("CHALLENGER-G1: contract-failed")
    elif challenger.get("status") == "retest-required":
        gaps.update(str(item) for item in challenger["missing_evidence_obligations"])
    else:
        gaps.add("no caller-authenticated challenger authority was exercised")
    if source_drift:
        fatal.add("repository changed after its opening HEAD/tree/content seal")
    document: dict[str, Any] = {
        "schema_version": 2,
        "fatal_findings": sorted(fatal),
        "development_gaps": sorted(gaps),
        "attacks": [
            "No aggregate score may compensate for one failed strict gate.",
            "A fixture winner is not a provider-backed or production-qualified agent.",
            "An authority manifest is not evaluator-owned holdout or surface evidence.",
            "A challenger proposal may not mutate, materialize, or promote itself.",
            "Every losing attempt and dissenting finding remains in the create-only bundle.",
        ],
        "dissent_preserved": True,
        "source_drift": source_drift,
        "final_inventory_digest": current_inventory["inventory_digest"],
        "final_repository_binding": current_binding,
    }
    document["receipt_digest"] = canonical_digest(document)
    return document


def _feedback_v2(
    role: str,
    role_grade: Mapping[str, Any],
    cross: Mapping[str, Any],
    challenger: Mapping[str, Any],
) -> dict[str, Any]:
    if role not in TOURNAMENT_ROLES:
        raise TournamentV2Error("feedback role is invalid")
    findings = [
        *[str(item) for item in role_grade.get("fatal_findings", ())],
        *[str(item) for item in role_grade.get("development_findings", ())],
        *[str(item) for item in cross.get("fatal_findings", ())],
        *[str(item) for item in cross.get("development_gaps", ())],
    ]
    obligations = challenger.get("missing_evidence_obligations", ())
    if isinstance(obligations, Sequence) and not isinstance(obligations, (str, bytes)):
        findings.extend(str(item) for item in obligations)
    challenger_finding = challenger.get("finding")
    if isinstance(challenger_finding, Mapping):
        findings.extend(
            str(challenger_finding[key])
            for key in ("summary", "proposed_change", "falsifier")
            if isinstance(challenger_finding.get(key), str)
        )
    findings = list(dict.fromkeys(findings))
    if not findings:
        findings = [f"challenge {role} beyond its current deterministic fixtures"]
    hypotheses = [
        f"Resolve without weakening an existing hard gate: {finding}"
        for finding in findings
    ]
    cycles: list[dict[str, Any]] = []
    current = hypotheses
    for number, stage in enumerate(
        (
            "reconsider-from-source-evidence",
            "attack-with-counterexamples",
            "seal-acceptance-rollback-and-fresh-reentry",
        ),
        start=1,
    ):
        input_hypotheses = list(current)
        if number == 2:
            current = [f"Seek a falsifying counterexample: {item}" for item in current]
        elif number == 3:
            current = [
                f"Bind an executable acceptance test and rollback, then re-scan: {item}"
                for item in current
            ]
        cycle: dict[str, Any] = {
            "cycle": number,
            "stage": stage,
            "input_digest": canonical_digest(
                {
                    "role_grade": role_grade.get("grade_digest")
                    or role_grade.get("receipt_digest"),
                    "cross_examination": _receipt_digest(cross),
                    "challenger": _receipt_digest(challenger),
                    "hypotheses": input_hypotheses,
                }
            ),
            "input_hypotheses": input_hypotheses,
            "output_hypotheses": list(current),
            "champion_mutated": False,
            "promotion_authorized": False,
        }
        cycle["cycle_digest"] = canonical_digest(cycle)
        cycles.append(cycle)
    document: dict[str, Any] = {
        "schema_version": 2,
        "role": role,
        "champion_ref": f"agent:{role}:current",
        "champion_grade_digest": role_grade.get("grade_digest")
        or role_grade.get("receipt_digest"),
        "initial_hypotheses": hypotheses,
        "challenger_hypotheses": current,
        "system_findings": [
            *cross.get("fatal_findings", ()),
            *cross.get("development_gaps", ()),
        ],
        "cycles": cycles,
        "cycles_executed": len(cycles),
        "immutable_champion": True,
        "promotion_authorized": False,
        "restart_nodes": [
            "SCAN-REPOSITORY",
            _role_node(role),
            *_STRICT_SYSTEM_NODES,
        ],
        "reentry": (
            "start a new create-only v2 run; generation-2 requires a retained genuine "
            "RETEST outcome or a separately judged DEFER appeal"
        ),
        "stop_conditions": [
            "a strict gate quarantines the generation",
            "three feedback cycles complete without admissible external evidence",
            "a genuine external authority or protected action gate is reached",
        ],
        "rollback": f"retain agent:{role}:current and every losing receipt",
    }
    document["feedback_digest"] = canonical_digest(document)
    return document


def _derive_report(
    receipts: Mapping[str, Mapping[str, Any]],
    *,
    plan_digest: str,
) -> dict[str, Any]:
    cross = receipts["CROSS-EXAMINE"]
    full_status = receipts["SYSTEM-FULL-SUITE"].get("status")
    fatal = [str(item) for item in cross.get("fatal_findings", ())]
    development = [str(item) for item in cross.get("development_gaps", ())]
    if cross.get("status") == "contract-failed":
        fatal.append("CROSS-EXAMINE: contract-failed")
    for role in TOURNAMENT_ROLES:
        if receipts[_feedback_node(role)].get("status") == "contract-failed":
            fatal.append(f"{_feedback_node(role)}: contract-failed")
    if fatal:
        disposition = "quarantine"
        whole_grade = "F"
    elif full_status == "deferred":
        disposition = "defer"
        whole_grade = "I"
    else:
        # All current role rubrics and the offline challenger remain explicitly
        # non-operational, so a green structural run is ADAPT rather than ADOPT.
        disposition = "adapt"
        whole_grade = "B"
    role_rows: list[dict[str, Any]] = []
    scores: list[int] = []
    for role in TOURNAMENT_ROLES:
        grade = receipts[_role_node(role)]
        if grade.get("role") == role and type(grade.get("score")) is int:
            score = int(grade["score"])
            scores.append(score)
            role_rows.append(
                {
                    "role": role,
                    "score": score,
                    "grade": grade["grade"],
                    "disposition": grade["court"]["disposition"],
                    "operationally_qualified": grade["operationally_qualified"],
                    "grade_digest": grade["grade_digest"],
                }
            )
        else:
            role_rows.append(
                {
                    "role": role,
                    "score": 0,
                    "grade": "F",
                    "disposition": "quarantine",
                    "operationally_qualified": False,
                    "grade_digest": grade["receipt_digest"],
                }
            )
            scores.append(0)
    system_rows = [
        {
            "node_id": node_id,
            "lane": receipts[node_id].get("lane", _LEGACY_SYSTEM_NODES.get(node_id)),
            "status": receipts[node_id].get("status"),
            "receipt_digest": _receipt_digest(receipts[node_id]),
        }
        for node_id in _STRICT_SYSTEM_NODES
    ]
    court = {
        "case_id": "CASE-AGENT-READINESS-TOURNAMENT-V2",
        "identities": {
            "advocate": "tournament-v2:advocate",
            "cross_examiner": "tournament-v2:cross-examiner",
            "expert_witness": "tournament-v2:expert",
            "curator": "tournament-v2:curator",
            "judge": "tournament-v2:judge",
            "affected_champion": "agent-set:current",
        },
        "identity_evidence": (
            "declared process roles only; authenticated independent principals are unproven"
        ),
        "disposition": disposition,
        "promotion_authorized": False,
        "dissent": development,
    }
    document: dict[str, Any] = {
        "schema_version": 2,
        "kind": "hive-mind-agent-readiness-tournament-v2-report",
        "plan_digest": plan_digest,
        "repository": {
            "head": receipts["SCAN-REPOSITORY"]["repository_binding"]["head_commit"],
            "tree": receipts["SCAN-REPOSITORY"]["repository_binding"]["tree_oid"],
            "state_digest": receipts["SCAN-REPOSITORY"]["repository_binding"][
                "state_digest"
            ],
            "inventory_digest": receipts["SCAN-REPOSITORY"]["inventory"][
                "inventory_digest"
            ],
        },
        "role_grades": role_rows,
        "role_average": round(sum(scores) / len(scores), 2),
        "whole_system_grade": whole_grade,
        "strict_system_gates": system_rows,
        "fatal_findings": fatal,
        "development_gaps": development,
        "code_qa": {
            "status": receipts["SYSTEM-CODE-QA-V2"].get("status"),
            "task_count": receipts["SYSTEM-CODE-QA-V2"].get("task_count", 0),
            "retained_losing_attempt_count": receipts["SYSTEM-CODE-QA-V2"].get(
                "retained_losing_attempt_count", 0
            ),
            "operationally_qualified": receipts["SYSTEM-CODE-QA-V2"].get(
                "operationally_qualified", False
            ),
        },
        "native_dag": {
            "status": receipts["SYSTEM-NATIVE-DAG"].get("status"),
            "native_role_count": len(
                receipts["SYSTEM-NATIVE-DAG"].get("native_roles", ())
            ),
            "max_observed_parallelism": receipts["SYSTEM-NATIVE-DAG"].get(
                "max_observed_parallelism", 0
            ),
            "integrator_steward_overlap": (
                receipts["SYSTEM-NATIVE-DAG"]
                .get("ready_set_overlap", {})
                .get("observed", False)
                if isinstance(
                    receipts["SYSTEM-NATIVE-DAG"].get("ready_set_overlap"), Mapping
                )
                else False
            ),
            "operationally_qualified": receipts["SYSTEM-NATIVE-DAG"].get(
                "operationally_qualified", False
            ),
            "semantic_outcomes": receipts["SYSTEM-NATIVE-DAG"].get(
                "semantic_outcomes", {}
            ),
        },
        "challenger": {
            "status": receipts["CHALLENGER-G1"].get("status"),
            "disposition": receipts["CHALLENGER-G1"].get("disposition"),
            "candidate_materialized": receipts["CHALLENGER-G1"].get(
                "candidate_materialized", False
            ),
            "promotion_authorized": False,
            "receipt_digest": _receipt_digest(receipts["CHALLENGER-G1"]),
        },
        "court": court,
        "comparison": {
            "status": "not-run",
            "winner": None,
            "reason": (
                "no equal-budget independently measured multi-comparator benchmark was supplied"
            ),
        },
        "qualification": (
            "Offline repository, deterministic fixture, and declared-role evidence only; "
            "not live-provider, arbitrary-repository, production, or superiority proof."
        ),
        "feedback_digests": [
            _receipt_digest(receipts[_feedback_node(role)]) for role in TOURNAMENT_ROLES
        ],
    }
    document["report_digest"] = canonical_digest(document)
    return document


def _render_report(report: Mapping[str, Any]) -> str:
    if report.get("status") == "contract-failed":
        return "\n".join(
            (
                "# Agent readiness tournament v2",
                "",
                "- Verdict: **QUARANTINE**",
                "- Whole-system grade: **F**",
                f"- Terminal error class: `{report.get('error_class', 'unknown')}`",
                "",
                "The championship node failed its contract; no adoption is authorized.",
                "",
            )
        )
    lines = [
        "# Agent readiness tournament v2",
        "",
        f"- Verdict: **{str(report['court']['disposition']).upper()}**",
        f"- Whole-system grade: **{report['whole_system_grade']}**",
        f"- Independent-role average: **{report['role_average']}/100**",
        f"- Report digest: `{report['report_digest']}`",
        "",
        "## Independent role grades",
        "",
        "| Role | Score | Grade | Disposition | Operationally qualified |",
        "|---|---:|:---:|---|:---:|",
    ]
    for row in report["role_grades"]:
        lines.append(
            f"| {row['role']} | {row['score']} | {row['grade']} | "
            f"{row['disposition']} | {str(row['operationally_qualified']).lower()} |"
        )
    lines.extend(
        (
            "",
            "## Non-compensating whole-system gates",
            "",
            "| Lane | Status |",
            "|---|---|",
        )
    )
    for row in report["strict_system_gates"]:
        lines.append(f"| {row['lane']} | {row['status']} |")
    native = report.get("native_dag")
    outcomes = native.get("semantic_outcomes") if isinstance(native, Mapping) else {}
    if isinstance(outcomes, Mapping) and outcomes:
        curator = outcomes.get("curator", {})
        integrator = outcomes.get("integrator", {})
        steward = outcomes.get("steward", {})
        optimizer = outcomes.get("optimizer", {})
        lines.extend(
            (
                "",
                "## Native composition outcomes",
                "",
                f"- Curator verdict: {curator.get('verdict') if isinstance(curator, Mapping) else None}",
                f"- Integrator status: {integrator.get('status') if isinstance(integrator, Mapping) else None}",
                f"- Steward readiness: {steward.get('readiness') if isinstance(steward, Mapping) else None}",
                f"- Steward unobserved surfaces: {steward.get('unobserved_surfaces') if isinstance(steward, Mapping) else None}",
                f"- Optimizer recommendation: {optimizer.get('recommendation') if isinstance(optimizer, Mapping) else None}",
                f"- Optimizer evidence complete: {optimizer.get('evidence_complete') if isinstance(optimizer, Mapping) else None}",
            )
        )
    lines.extend(("", "## Preserved findings", ""))
    findings = [*report["fatal_findings"], *report["development_gaps"]]
    lines.extend(f"- {finding}" for finding in findings)
    lines.extend(("", "## Qualification", "", str(report["qualification"]), ""))
    return "\n".join(lines)


def _manifest(run_root: Path, *, exclude_root_manifest: bool = True) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    directories: list[str] = []
    total = 0
    for path in sorted(run_root.rglob("*"), key=lambda value: value.as_posix()):
        if len(rows) + len(directories) >= _MAX_MANIFEST_ENTRIES:
            raise TournamentV2Error("run evidence exceeds its entry budget")
        if v1._is_link_like(path):
            raise TournamentV2Error("run evidence contains a link or junction")
        if path.is_dir():
            directories.append(path.relative_to(run_root).as_posix())
            continue
        if not path.is_file():
            raise TournamentV2Error("run evidence contains an unsupported entry")
        if exclude_root_manifest and path == run_root / "manifest.json":
            continue
        size = path.stat().st_size
        total += size
        if size > _MAX_ARTIFACT_BYTES or total > _MAX_BUNDLE_BYTES:
            raise TournamentV2Error("run evidence exceeds its bounded artifact budget")
        rows.append(
            {
                "path": path.relative_to(run_root).as_posix(),
                "bytes": size,
                "sha256": _sha256_file(path),
            }
        )
    document: dict[str, Any] = {
        "schema_version": 2,
        "directories": directories,
        "files": rows,
    }
    document["manifest_digest"] = canonical_digest(document)
    return document


def _observed_peak(attempts: Mapping[str, Sequence[Mapping[str, Any]]]) -> int:
    edges: list[tuple[str, int]] = []
    for rows in attempts.values():
        for row in rows:
            edges.append((str(row["started_at"]), 1))
            edges.append((str(row["ended_at"]), -1))
    active = peak = 0
    for _moment, delta in sorted(edges, key=lambda item: (item[0], item[1])):
        active += delta
        peak = max(peak, active)
    return peak


def _execute_node(
    node: Mapping[str, Any],
    *,
    repository: Path,
    run_root: Path,
    receipts: Mapping[str, Mapping[str, Any]],
    full_suite: bool,
    command_runner: CommandRunner,
    authority_path: Path | None,
    authority_digest: str | None,
) -> tuple[dict[str, Any], str | None]:
    node_id = str(node["node_id"])
    action = str(node["action"])
    scan = receipts["SCAN-REPOSITORY"]
    inventory = scan["inventory"]
    if action == "grade-role":
        return v1.grade_role(repository, str(node["role"]), command_runner)
    if node_id == "SYSTEM-STATIC":
        return v1.static_repository_gate(repository, inventory), None
    if node_id in {
        "SYSTEM-LIFECYCLE",
        "SYSTEM-RESILIENCE",
        "SYSTEM-EVOLUTION",
    }:
        lane = str(node["lane"])
        return v1._test_lane(
            repository,
            lane,
            v1.SYSTEM_TEST_LANES[lane],
            command_runner,
        )
    if node_id == "SYSTEM-CONTROL-PLANE":
        return v1.control_plane_gate(repository, command_runner)
    if node_id == "SYSTEM-CONTROL-PLANE-TESTS":
        return v1.control_plane_tests_gate(repository, command_runner)
    if node_id == "SYSTEM-NATIVE-DAG":
        return _run_native_dag(repository, run_root, scan, command_runner)
    if node_id == "SYSTEM-CODE-QA-V2":
        return _run_code_qa(repository, run_root), None
    if node_id == "SYSTEM-CONTROL-PLANE-DOCTOR":
        return v1.control_plane_doctor_gate(
            repository,
            command_runner,
            inventory=inventory,
        )
    if node_id == "CHALLENGER-G1":
        return (
            _authority_challenger(
                repository,
                run_root,
                receipts,
                authority_path=authority_path,
                authority_digest=authority_digest,
            ),
            None,
        )
    if node_id == "SYSTEM-FULL-SUITE":
        return _full_suite_v2(repository, full_suite, command_runner)
    if node_id == "CROSS-EXAMINE":
        return _cross_examine_v2(repository, receipts), None
    if action == "feedback":
        return (
            _feedback_v2(
                str(node["role"]),
                receipts[_role_node(str(node["role"]))],
                receipts["CROSS-EXAMINE"],
                receipts["CHALLENGER-G1"],
            ),
            None,
        )
    if node_id == "CHAMPIONSHIP":
        return (
            _derive_report(
                receipts,
                plan_digest=build_tournament_plan_v2()["plan_digest"],
            ),
            None,
        )
    raise TournamentV2Error(f"unsupported v2 node: {node_id}")


def _full_suite_v2(
    repository: Path,
    enabled: bool,
    command_runner: CommandRunner,
) -> tuple[dict[str, Any], str | None]:
    """Run canonical discovery through the runner sealed by V2's SCAN receipt."""

    if not enabled:
        return v1._full_suite(repository, False)
    if command_runner is _BUILTIN_COMMAND_RUNNER:
        receipt, transcript = _BUILTIN_RECEIPT_RUNNER(
            repository,
            v1._FULL_SUITE_COMMAND,
            timeout_seconds=3600,
        )
    else:
        receipt, transcript = command_runner(repository, v1._FULL_SUITE_COMMAND)
    document: dict[str, Any] = {
        "lane": "full-suite",
        "status": receipt["status"],
        "critical": receipt["status"] != "passed",
        "command_receipt": receipt,
    }
    document["receipt_digest"] = canonical_digest(document)
    return document, transcript


def run_tournament_v2(
    repository: str | Path,
    output_directory: str | Path,
    *,
    max_workers: int = 8,
    full_suite: bool = True,
    plan: Mapping[str, Any] | None = None,
    authority_manifest: str | Path | None = None,
    authority_digest: str | None = None,
    command_runner: CommandRunner = _BUILTIN_COMMAND_RUNNER,
) -> dict[str, Any]:
    """Execute the canonical v2 DAG into a previously absent directory.

    A non-default ``command_runner`` is a test-only seam.  Its identity is
    retained and the resulting run is unconditionally quarantined.
    """

    if not 2 <= max_workers <= len(TOURNAMENT_ROLES):
        raise TournamentV2Error(
            f"max_workers must be between 2 and {len(TOURNAMENT_ROLES)}"
        )
    if (authority_manifest is None) != (authority_digest is None):
        raise TournamentV2Error(
            "authority manifest and caller-expected digest must be supplied together"
        )
    selected_plan = dict(plan or build_tournament_plan_v2())
    waves = validate_tournament_plan_v2(selected_plan)
    repository_root = Path(repository).resolve(strict=True)
    if (
        Path(__file__).resolve().parent
        != (repository_root / "src/hive_mind_os").resolve()
    ):
        raise TournamentV2Error(
            "v2 runtime was not imported from the selected repository"
        )
    raw_output = Path(output_directory).absolute()
    if os.path.lexists(raw_output):
        raise TournamentV2Error(
            f"output directory must not already exist: {raw_output}"
        )
    if not raw_output.parent.is_dir():
        raise TournamentV2Error("output directory parent must already exist")
    if v1._has_link_like_component(Path(raw_output.anchor), raw_output.parent):
        raise TournamentV2Error("output path contains a symbolic link or junction")
    run_root = raw_output.resolve()
    _require_disjoint_roots(
        repository_root, run_root, label="v2 tournament output directory"
    )
    opening_inventory = v1.inventory_repository(repository_root)
    v1._validate_path_outside_authority(
        run_root,
        v1._source_authority_roots(repository_root, opening_inventory),
        label="v2 tournament output directory",
    )
    # SCAN is a bootstrap precondition: complete it before creating the bundle so
    # a seal failure cannot strand an unverifiable partial run directory.
    scan_started = _now()
    scan_clock = time.monotonic()
    scan = _scan_receipt(
        repository_root, opening_inventory, command_runner=command_runner
    )
    run_root.mkdir()
    for directory in ("receipts", "transcripts", "waves"):
        (run_root / directory).mkdir()
    _write_json_create(run_root / "plan.json", selected_plan)

    receipts: dict[str, dict[str, Any]] = {}
    event_path = run_root / "events.jsonl"
    previous_event: str | None = None

    def record(node_id: str, receipt: dict[str, Any], transcript: str | None) -> None:
        nonlocal previous_event
        _write_json_create(run_root / "receipts" / f"{node_id}.json", receipt)
        if transcript is not None:
            _write_text_create(run_root / "transcripts" / f"{node_id}.txt", transcript)
        event: dict[str, Any] = {
            "sequence": len(receipts) + 1,
            "node_id": node_id,
            "status": "completed",
            "receipt_digest": _receipt_digest(receipt),
            "previous_event_digest": previous_event,
        }
        event["event_digest"] = canonical_digest(event)
        with event_path.open("ab") as stream:
            stream.write(
                (
                    json.dumps(
                        event,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                ).encode("utf-8")
            )
        previous_event = str(event["event_digest"])
        receipts[node_id] = receipt

    scan_attempt = {
        "attempt": 1,
        "started_at": scan_started,
        "ended_at": _now(),
        "duration_ms": round((time.monotonic() - scan_clock) * 1000),
        "outcome": "completed",
    }
    scan_wave: dict[str, Any] = {
        "wave": 1,
        "nodes": ["SCAN-REPOSITORY"],
        "parallel": False,
        "workers_used": 1,
        "attempts": {"SCAN-REPOSITORY": [scan_attempt]},
        "observed_peak_concurrency": _observed_peak(
            {"SCAN-REPOSITORY": [scan_attempt]}
        ),
        "status": "completed",
    }
    scan_wave["wave_digest"] = canonical_digest(scan_wave)
    _write_json_create(run_root / "waves" / "wave-01.json", scan_wave)
    record("SCAN-REPOSITORY", scan, None)

    node_by_id = {str(node["node_id"]): node for node in selected_plan["nodes"]}
    for wave_number, wave in enumerate(waves[1:], start=2):
        workers = min(max_workers, len(wave))
        attempts: dict[str, list[dict[str, Any]]] = {}
        completed: dict[str, tuple[dict[str, Any], str | None]] = {}
        wave_barrier = (
            threading.Barrier(workers, timeout=30)
            if len(wave) > 1 and workers > 1
            else None
        )
        barrier_nodes = frozenset(wave[:workers])

        def invoke(node_id: str) -> tuple[dict[str, Any], str | None, dict[str, Any]]:
            started = _now()
            clock = time.monotonic()
            try:
                if wave_barrier is not None and node_id in barrier_nodes:
                    # The first worker cohort proves overlap without forcing a
                    # partial final cohort through a reusable barrier.
                    wave_barrier.wait()
                receipt, transcript = _execute_node(
                    node_by_id[node_id],
                    repository=repository_root,
                    run_root=run_root,
                    receipts=receipts,
                    full_suite=full_suite,
                    command_runner=command_runner,
                    authority_path=(
                        None
                        if authority_manifest is None
                        else Path(authority_manifest).absolute()
                    ),
                    authority_digest=authority_digest,
                )
                outcome = str(receipt.get("status", "completed"))
            except Exception as error:  # evidence must survive every typed failure
                artifact_directory = {
                    "SYSTEM-NATIVE-DAG": run_root / "native-dag",
                    "SYSTEM-CODE-QA-V2": run_root / "code-qa",
                    "CHALLENGER-G1": run_root / "challenger",
                }.get(node_id)
                if artifact_directory is not None and os.path.lexists(
                    artifact_directory
                ):
                    artifact_identity = v1._owned_cleanup_identity(artifact_directory)
                    v1._remove_disposable_tree(
                        artifact_directory, expected_identity=artifact_identity
                    )
                receipt, transcript = _generic_failure(node_id, error), None
                outcome = "contract-failed"
            attempt = {
                "attempt": 1,
                "started_at": started,
                "ended_at": _now(),
                "duration_ms": round((time.monotonic() - clock) * 1000),
                "outcome": outcome,
            }
            return receipt, transcript, attempt

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(invoke, node_id): node_id for node_id in wave}
            for future in as_completed(futures):
                node_id = futures[future]
                receipt, transcript, attempt = future.result()
                completed[node_id] = (receipt, transcript)
                attempts[node_id] = [attempt]
        wave_record: dict[str, Any] = {
            "wave": wave_number,
            "nodes": list(wave),
            "parallel": len(wave) > 1 and workers > 1,
            "workers_used": workers,
            "attempts": {node_id: attempts[node_id] for node_id in wave},
            "observed_peak_concurrency": _observed_peak(attempts),
            "status": "completed",
        }
        wave_record["wave_digest"] = canonical_digest(wave_record)
        _write_json_create(
            run_root / "waves" / f"wave-{wave_number:02d}.json", wave_record
        )
        for node_id in wave:
            receipt, transcript = completed[node_id]
            record(node_id, receipt, transcript)

    report = receipts["CHAMPIONSHIP"]
    _write_json_create(run_root / "report.json", report)
    _write_text_create(run_root / "report.md", _render_report(report))
    _write_json_create(run_root / "manifest.json", _manifest(run_root))
    return verify_run_directory_v2(
        run_root,
        repository=repository_root,
        authority_manifest=authority_manifest,
        authority_digest=authority_digest,
    )


def _validate_generic_failure(node_id: str, receipt: Mapping[str, Any]) -> bool:
    if receipt.get("status") != "contract-failed":
        return False
    if set(receipt) != {
        "node_id",
        "status",
        "critical",
        "error_class",
        "error",
        "receipt_digest",
    }:
        raise TournamentV2Error(f"{node_id} contract-failure fields are invalid")
    if (
        receipt.get("node_id") != node_id
        or receipt.get("critical") is not True
        or not isinstance(receipt.get("error_class"), str)
        or not isinstance(receipt.get("error"), str)
    ):
        raise TournamentV2Error(f"{node_id} contract-failure receipt is invalid")
    _self_digest(receipt, "receipt_digest")
    return True


def _validate_manifest(run_root: Path) -> Mapping[str, Any]:
    manifest_path = run_root / "manifest.json"
    if not manifest_path.is_file() or v1._is_link_like(manifest_path):
        raise TournamentV2Error("v2 manifest is unavailable")
    if manifest_path.stat().st_size > _MAX_ARTIFACT_BYTES:
        raise TournamentV2Error("v2 manifest exceeds its artifact budget")
    manifest = _strict_json(manifest_path)
    if set(manifest) != {
        "schema_version",
        "directories",
        "files",
        "manifest_digest",
    }:
        raise TournamentV2Error("v2 manifest fields are invalid")
    if manifest.get("schema_version") != 2:
        raise TournamentV2Error("v2 manifest schema is invalid")
    _self_digest(manifest, "manifest_digest")
    rows = manifest.get("files")
    if not isinstance(rows, list):
        raise TournamentV2Error("v2 manifest file inventory is invalid")
    if len(rows) > _MAX_MANIFEST_ENTRIES:
        raise TournamentV2Error("v2 manifest exceeds its entry budget")
    listed: dict[str, Mapping[str, Any]] = {}
    total = 0
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {"path", "bytes", "sha256"}:
            raise TournamentV2Error("v2 manifest contains a malformed row")
        relative = row.get("path")
        if (
            not isinstance(relative, str)
            or not relative
            or Path(relative).is_absolute()
            or Path(relative).as_posix() != relative
            or ".." in Path(relative).parts
            or relative in listed
            or type(row.get("bytes")) is not int
            or int(row["bytes"]) < 0
            or not isinstance(row.get("sha256"), str)
            or _DIGEST.fullmatch(str(row["sha256"])) is None
        ):
            raise TournamentV2Error("v2 manifest row is invalid")
        total += int(row["bytes"])
        if int(row["bytes"]) > _MAX_ARTIFACT_BYTES or total > _MAX_BUNDLE_BYTES:
            raise TournamentV2Error("v2 manifest exceeds its evidence budget")
        listed[relative] = row
    if list(listed) != sorted(listed):
        raise TournamentV2Error("v2 manifest file rows are not canonical")
    entries = list(run_root.rglob("*"))
    if any(v1._is_link_like(path) for path in entries):
        raise TournamentV2Error("v2 bundle contains a link or junction")
    allowed_top = {
        "receipts",
        "transcripts",
        "waves",
        "native-dag",
        "code-qa",
        "challenger",
    }
    allowed_root_files = {"events.jsonl", "plan.json", "report.json", "report.md"}
    for path in entries:
        relative = path.relative_to(run_root)
        if (
            (
                len(relative.parts) == 1
                and path.is_dir()
                and relative.name not in allowed_top
            )
            or (
                len(relative.parts) == 1
                and path.is_file()
                and relative.name not in allowed_root_files
                and path != manifest_path
            )
            or (len(relative.parts) > 1 and relative.parts[0] not in allowed_top)
        ):
            raise TournamentV2Error("v2 bundle contains an unknown directory tree")
    directory_rows = manifest.get("directories")
    if (
        not isinstance(directory_rows, list)
        or any(not isinstance(value, str) for value in directory_rows)
        or directory_rows != sorted(set(directory_rows))
        or len(directory_rows) + len(rows) > _MAX_MANIFEST_ENTRIES
    ):
        raise TournamentV2Error("v2 manifest directory inventory is invalid")
    observed_directories = sorted(
        path.relative_to(run_root).as_posix() for path in entries if path.is_dir()
    )
    if directory_rows != observed_directories:
        raise TournamentV2Error("v2 manifest does not exactly cover directories")
    observed = {
        path.relative_to(run_root).as_posix(): path
        for path in entries
        if path.is_file() and path != manifest_path
    }
    if set(observed) != set(listed):
        raise TournamentV2Error("v2 manifest does not exactly cover the bundle")
    for relative, path in observed.items():
        row = listed[relative]
        if path.stat().st_size != row["bytes"] or _sha256_file(path) != row["sha256"]:
            raise TournamentV2Error(f"v2 artifact differs from manifest: {relative}")
    return manifest


def _validate_scan(scan: Mapping[str, Any], repository: Path) -> Mapping[str, Any]:
    if set(scan) != {
        "schema_version",
        "kind",
        "inventory",
        "repository_binding",
        "execution",
        "receipt_digest",
    }:
        raise TournamentV2Error("repository seal fields are invalid")
    if (
        scan.get("schema_version") != 2
        or scan.get("kind") != "hive-mind-agent-readiness-repository-seal-v2"
    ):
        raise TournamentV2Error("repository seal schema is invalid")
    _self_digest(scan, "receipt_digest")
    inventory = scan.get("inventory")
    if not isinstance(inventory, Mapping):
        raise TournamentV2Error("repository seal inventory is invalid")
    inventory_material = dict(inventory)
    supplied_inventory = inventory_material.pop("inventory_digest", None)
    if supplied_inventory != canonical_digest(inventory_material):
        raise TournamentV2Error("repository inventory digest is invalid")
    if inventory.get("repository_root") != str(repository):
        raise TournamentV2Error("repository seal is bound to another checkout")
    binding = scan.get("repository_binding")
    if not isinstance(binding, Mapping) or set(binding) != {
        "head_commit",
        "tree_oid",
        "state_digest",
    }:
        raise TournamentV2Error("repository HEAD/tree/state binding is invalid")
    execution = scan.get("execution")
    if not isinstance(execution, Mapping) or set(execution) != {
        "runtime_path",
        "runtime_sha256",
        "command_runner_identity",
        "trusted_builtin_command_runner",
    }:
        raise TournamentV2Error("repository execution binding is invalid")
    runtime_rows = {
        str(row.get("path")): row.get("sha256")
        for row in inventory.get("files", ())
        if isinstance(row, Mapping)
    }
    if (
        execution.get("runtime_path") != _RUNTIME_PATH
        or execution.get("runtime_sha256") != runtime_rows.get(_RUNTIME_PATH)
        or not isinstance(execution.get("command_runner_identity"), str)
        or not execution.get("command_runner_identity")
        or not isinstance(execution.get("trusted_builtin_command_runner"), bool)
        or (
            execution.get("trusted_builtin_command_runner") is True
            and execution.get("command_runner_identity")
            != _BUILTIN_COMMAND_RUNNER_IDENTITY
        )
    ):
        raise TournamentV2Error("repository runtime binding is invalid")
    live_inventory = v1.inventory_repository(repository)
    live_binding = asdict(capture_repository_binding(repository))
    if canonical_digest(live_inventory) != canonical_digest(inventory):
        raise TournamentV2Error("repository content drifted after the v2 seal")
    if live_binding != dict(binding):
        raise TournamentV2Error("repository HEAD/tree/state drifted after the v2 seal")
    return inventory


def _validate_code_qa(
    receipt: Mapping[str, Any], repository: Path, run_root: Path
) -> None:
    if _validate_generic_failure("SYSTEM-CODE-QA-V2", receipt):
        if (run_root / "code-qa").exists():
            raise TournamentV2Error("failed code-QA lane retained untyped artifacts")
        return
    expected_fields = {
        "lane",
        "status",
        "critical",
        "fixture_root",
        "corpus_run_path",
        "corpus_run_sha256",
        "corpus_digest",
        "bundle_digest",
        "pin_mode",
        "scope",
        "expected_task_ids",
        "selected_task_ids",
        "task_contract_digests",
        "evaluator_id",
        "qualification",
        "operationally_qualified",
        "independent_evaluator",
        "adaptive_intelligence",
        "trust_model",
        "limitations",
        "task_count",
        "retained_losing_attempt_count",
        "tasks",
        "receipt_digest",
    }
    if set(receipt) != expected_fields:
        raise TournamentV2Error("code-QA receipt fields are invalid")
    _self_digest(receipt, "receipt_digest")
    corpus_path = run_root / str(receipt["corpus_run_path"])
    if (
        receipt.get("lane") != "code-qa-v2"
        or receipt.get("fixture_root") != _FIXTURE_ROOT
        or receipt.get("corpus_run_path") != "code-qa/corpus-run.json"
        or not corpus_path.is_file()
        or receipt.get("corpus_run_sha256") != _sha256_file(corpus_path)
        or receipt.get("operationally_qualified") is not False
        or receipt.get("independent_evaluator") is not False
        or receipt.get("adaptive_intelligence") is not False
        or receipt.get("bundle_digest") != PINNED_CORPUS_BUNDLE_DIGEST
        or receipt.get("scope") != "complete-bounded-corpus"
    ):
        raise TournamentV2Error("code-QA receipt binding is invalid")
    with tempfile.TemporaryDirectory(prefix="hmtv2-verify-") as temporary:
        replay_root = Path(temporary).resolve() / "code-qa"
        replay = run_code_qa_corpus(
            repository / _FIXTURE_ROOT,
            replay_root,
            expected_bundle_digest=PINNED_CORPUS_BUNDLE_DIGEST,
        )
        expected = _code_qa_summary(replay, Path(temporary).resolve())
        replay_tree = _manifest(replay_root, exclude_root_manifest=False)
    actual_tree = _manifest(run_root / "code-qa", exclude_root_manifest=False)
    if (
        receipt != expected
        or actual_tree["directories"] != replay_tree["directories"]
        or actual_tree["files"] != replay_tree["files"]
    ):
        raise TournamentV2Error(
            "code-QA receipt is not reproducible from sealed fixtures"
        )


def _validate_native_dag(
    receipt: Mapping[str, Any],
    repository: Path,
    run_root: Path,
    scan: Mapping[str, Any],
    transcript: str | None,
) -> None:
    node_id = "SYSTEM-NATIVE-DAG"
    if _validate_generic_failure(node_id, receipt):
        if (run_root / "native-dag").exists() or transcript is not None:
            raise TournamentV2Error("failed native DAG retained untyped artifacts")
        return
    expected_fields = {
        "lane",
        "status",
        "critical",
        "plan",
        "plan_digest",
        "candidate_digest",
        "node_receipts",
        "events",
        "logical_digest",
        "max_observed_parallelism",
        "ready_set_overlap",
        "native_roles",
        "native_symbols",
        "executor_ids",
        "semantic_outcomes",
        "snapshot",
        "artifact_store_root",
        "workspace_cleanup_completed",
        "test_modules",
        "test_receipt",
        "operationally_qualified",
        "isolation_assurance",
        "limitations",
        "receipt_digest",
    }
    if set(receipt) != expected_fields:
        raise TournamentV2Error("native DAG receipt fields are invalid")
    _self_digest(receipt, "receipt_digest")
    inventory = scan["inventory"]
    plan = repository_specialist_plan(plan_id="agent-readiness-tournament-v2")
    snapshot = receipt.get("snapshot")
    if not isinstance(snapshot, Mapping) or set(snapshot) != {
        "temporary_path",
        "before",
        "after",
        "file_set_digest",
        "git_line_ending_mode",
        "cleanup_completed",
    }:
        raise TournamentV2Error("native DAG snapshot evidence is invalid")
    before = snapshot.get("before")
    after = snapshot.get("after")
    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        raise TournamentV2Error("native DAG snapshot bindings are invalid")
    expected_candidate = repository_candidate_digest(repository, plan.digest)
    temporary_path = Path(str(snapshot.get("temporary_path")))
    expected_temporary_parent = v1._validated_ambient_temp_root(
        v1._source_authority_roots(repository, inventory)
    ).resolve()
    if (
        receipt.get("lane") != "native-dag"
        or receipt.get("plan") != plan.to_document()
        or receipt.get("plan_digest") != plan.digest
        or receipt.get("candidate_digest") != expected_candidate
        or before != after
        or dict(before) != scan["repository_binding"]
        or before.get("state_digest") != canonical_digest({"status": [], "diff": ""})
        or snapshot.get("file_set_digest") != _repository_file_set_digest(inventory)
        or snapshot.get("git_line_ending_mode") not in {"false", "true", "input"}
        or snapshot.get("cleanup_completed") is not True
        or not temporary_path.is_absolute()
        or temporary_path != temporary_path.resolve(strict=False)
        or temporary_path.parent != expected_temporary_parent
        or not temporary_path.name.startswith("hnd-v2-")
        or os.path.lexists(temporary_path)
        or temporary_path == repository
        or temporary_path.is_relative_to(repository)
        or temporary_path == run_root
        or temporary_path.is_relative_to(run_root)
        or receipt.get("artifact_store_root") != "native-dag/evidence"
        or receipt.get("workspace_cleanup_completed") is not True
        or (run_root / "native-dag" / "workspaces").exists()
        or receipt.get("operationally_qualified") is not False
        or receipt.get("isolation_assurance") != ISOLATION_ASSURANCE
    ):
        raise TournamentV2Error("native DAG source/isolation binding is inconsistent")

    raw_receipts = receipt.get("node_receipts")
    if not isinstance(raw_receipts, list) or len(raw_receipts) != 8:
        raise TournamentV2Error("native DAG node receipt inventory is invalid")
    expected_order = plan.topological_order
    by_node = {node.node_id: node for node in plan.nodes}
    store = ArtifactStore(run_root / "native-dag" / "evidence")
    restored: list[NodeReceipt] = []
    restored_by_node: dict[str, NodeReceipt] = {}
    payloads: dict[str, Mapping[str, Any]] = {}
    expected_node_fields = {
        "plan_digest",
        "candidate_digest",
        "node_id",
        "role",
        "executor_id",
        "status",
        "dependency_artifact_digests",
        "artifact_digest",
        "native_evidence",
        "invoked_symbol",
        "written_paths",
        "error_type",
        "error_message",
        "isolation_assurance",
        "receipt_digest",
    }
    for index, row in enumerate(raw_receipts):
        if not isinstance(row, Mapping) or set(row) != expected_node_fields:
            raise TournamentV2Error("native DAG contains a malformed node receipt")
        if row.get("node_id") != expected_order[index]:
            raise TournamentV2Error("native DAG node receipt order is invalid")
        native_node = by_node[expected_order[index]]
        try:
            restored_receipt = NodeReceipt(
                plan_digest=str(row["plan_digest"]),
                candidate_digest=str(row["candidate_digest"]),
                node_id=str(row["node_id"]),
                role=str(row["role"]),
                executor_id=str(row["executor_id"]),
                status=NodeStatus(str(row["status"])),
                dependency_artifact_digests=tuple(
                    str(value) for value in row["dependency_artifact_digests"]
                ),
                artifact_digest=(
                    None
                    if row["artifact_digest"] is None
                    else str(row["artifact_digest"])
                ),
                native_evidence=bool(row["native_evidence"]),
                invoked_symbol=(
                    None
                    if row["invoked_symbol"] is None
                    else str(row["invoked_symbol"])
                ),
                written_paths=tuple(str(value) for value in row["written_paths"]),
                error_type=None
                if row["error_type"] is None
                else str(row["error_type"]),
                error_message=(
                    None if row["error_message"] is None else str(row["error_message"])
                ),
                isolation_assurance=str(row["isolation_assurance"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise TournamentV2Error("native DAG node receipt is invalid") from error
        if (
            restored_receipt.to_document()
            != {key: value for key, value in row.items() if key != "receipt_digest"}
            or restored_receipt.receipt_digest != row.get("receipt_digest")
            or restored_receipt.plan_digest != plan.digest
            or restored_receipt.candidate_digest != expected_candidate
            or restored_receipt.role != native_node.role
            or restored_receipt.executor_id != native_node.executor_id
        ):
            raise TournamentV2Error("native DAG node receipt is not plan-derived")
        expected_dependencies = tuple(
            sorted(
                predecessor.artifact_digest
                for dependency in native_node.dependencies
                if (predecessor := restored_by_node[dependency]).artifact_digest
                is not None
            )
        )
        adverse_dependencies = tuple(
            dependency
            for dependency in native_node.dependencies
            if restored_by_node[dependency].status is not NodeStatus.SUCCEEDED
        )
        if restored_receipt.dependency_artifact_digests != expected_dependencies:
            raise TournamentV2Error(
                "native DAG dependency digests are not predecessor-derived"
            )
        if adverse_dependencies and (
            restored_receipt.status is not NodeStatus.BLOCKED
            or restored_receipt.error_type != "DependencyFailed"
            or restored_receipt.error_message
            != "blocked by adverse dependency receipts: "
            + ", ".join(sorted(adverse_dependencies))
        ):
            raise TournamentV2Error(
                "native DAG failed dependency did not block its child"
            )
        try:
            write_paths_are_scoped = all(
                normalize_portable_path(path) == path
                and any(
                    path == scope or path.startswith(scope + "/")
                    for scope in native_node.write_scope
                )
                for path in restored_receipt.written_paths
            )
        except (TypeError, ValueError):
            write_paths_are_scoped = False
        if not write_paths_are_scoped:
            raise TournamentV2Error("native DAG node wrote beyond its declared scope")
        if restored_receipt.status is NodeStatus.SUCCEEDED:
            if (
                restored_receipt.native_evidence is not True
                or restored_receipt.invoked_symbol != native_node.native_symbol
                or restored_receipt.artifact_digest is None
            ):
                raise TournamentV2Error(
                    "successful native node lacks direct API evidence"
                )
            try:
                stored = store.read(restored_receipt.artifact_digest)
            except (KeyError, OSError, ValueError) as error:
                raise TournamentV2Error(
                    "native DAG artifact failed content-addressed verification"
                ) from error
            envelope = stored.envelope
            if (
                envelope.candidate_digest != expected_candidate
                or envelope.media_type != native_node.produces.media_type
                or envelope.schema_id != native_node.produces.schema_id
                or envelope.schema_version != native_node.produces.schema_version
                or envelope.schema_digest != native_node.produces.schema_digest
                or envelope.producer_id != native_node.executor_id
                or envelope.dependency_digests
                != restored_receipt.dependency_artifact_digests
            ):
                raise TournamentV2Error("native DAG artifact envelope is misbound")
            try:
                content = json.loads(
                    stored.content.decode("utf-8"),
                    object_pairs_hook=v1._reject_duplicate_object_pairs,
                    parse_constant=_reject_json_constant,
                )
            except (UnicodeError, json.JSONDecodeError, ValueError) as error:
                raise TournamentV2Error(
                    "native DAG artifact is not canonical JSON"
                ) from error
            if (
                not isinstance(content, Mapping)
                or canonical_bytes(content) != stored.content
            ):
                raise TournamentV2Error("native DAG artifact is not canonical JSON")
            artifact_hex = restored_receipt.artifact_digest.removeprefix("sha256:")
            artifact_path = (
                run_root
                / "native-dag"
                / "evidence"
                / "artifacts"
                / "sha256"
                / artifact_hex[:2]
                / f"{artifact_hex}.json"
            )
            artifact_document = _strict_json(artifact_path)
            if canonical_bytes(artifact_document) != artifact_path.read_bytes():
                raise TournamentV2Error("native DAG artifact bundle is not canonical")
            _validate_native_payload(
                native_node.role, content, scan["repository_binding"]
            )
            payloads[native_node.role] = content
        elif (
            restored_receipt.artifact_digest is not None
            or restored_receipt.native_evidence
            or restored_receipt.invoked_symbol is not None
        ):
            raise TournamentV2Error("adverse native node claims successful evidence")
        restored.append(restored_receipt)
        restored_by_node[restored_receipt.node_id] = restored_receipt

    if {"architect", "builder", "curator"} <= set(payloads):
        builder_payload = payloads["builder"]
        curator_payload = payloads["curator"]
        validation = curator_payload.get("builder_validation")
        smoke = curator_payload.get("smoke_test")
        presence = curator_payload.get("test_presence")
        builder_receipt = next(row for row in restored if row.role == "builder")
        architect_receipt = next(row for row in restored if row.role == "architect")
        builder_actions = builder_payload.get("actions")
        if not isinstance(builder_actions, list):
            raise TournamentV2Error("native Builder action evidence is invalid")
        action_receipts = sorted(
            str(row["effect_receipt_digest"])
            for row in builder_actions
            if isinstance(row, Mapping)
        )
        if (
            not isinstance(validation, Mapping)
            or set(validation)
            != {
                "passed",
                "builder_artifact_digest",
                "product_path",
                "product_digest",
                "architecture_artifact_digest",
                "action_receipt_digests",
                "error_type",
            }
            or validation.get("passed") is not True
            or validation.get("builder_artifact_digest")
            != builder_receipt.artifact_digest
            or validation.get("product_path")
            != builder_payload.get("workspace_product")
            or validation.get("product_digest")
            != builder_payload.get("workspace_product_digest")
            or validation.get("architecture_artifact_digest")
            != architect_receipt.artifact_digest
            or validation.get("action_receipt_digests") != action_receipts
            or validation.get("error_type") is not None
            or presence != {"passed": True, "pattern": "tests/test_*.py"}
            or not isinstance(smoke, Mapping)
            or set(smoke)
            != {
                "check_id",
                "module",
                "argv",
                "passed",
                "returncode",
                "tests_run",
                "stdout_digest",
                "stderr_digest",
                "error_type",
            }
            or smoke.get("check_id") != "repository-nonrecursive-smoke"
            or smoke.get("module") != "tests.test_brain_kernel_artifacts"
            or smoke.get("argv")
            != [
                "python",
                "-B",
                "-m",
                "unittest",
                "tests.test_brain_kernel_artifacts",
            ]
            or smoke.get("passed") is not True
            or smoke.get("returncode") != 0
            or type(smoke.get("tests_run")) is not int
            or int(smoke["tests_run"]) < 1
            or any(
                not isinstance(smoke.get(key), str)
                or _DIGEST.fullmatch(str(smoke[key])) is None
                for key in ("stdout_digest", "stderr_digest")
            )
            or smoke.get("error_type") is not None
        ):
            raise TournamentV2Error("native Curator evidence is not Builder-bound")

    raw_events = receipt.get("events")
    if not isinstance(raw_events, list) or len(raw_events) != 8:
        raise TournamentV2Error("native DAG event inventory is invalid")
    previous: str | None = None
    event_digests: list[str] = []
    for sequence, (raw_event, node_receipt) in enumerate(
        zip(raw_events, restored), start=1
    ):
        expected_event = DagEvent.create(
            sequence=sequence,
            receipt=node_receipt,
            previous_digest=previous,
        )
        if not isinstance(raw_event, Mapping) or dict(raw_event) != asdict(
            expected_event
        ):
            raise TournamentV2Error("native DAG event chain is not derivable")
        previous = expected_event.event_digest
        event_digests.append(previous)
    expected_logical = canonical_digest(
        {
            "plan_digest": plan.digest,
            "candidate_digest": expected_candidate,
            "event_digests": event_digests,
        }
    )
    integrator = next(node for node in plan.nodes if node.role == "integrator")
    steward = next(node for node in plan.nodes if node.role == "steward")
    observed_parallelism = receipt.get("max_observed_parallelism")
    if (
        type(observed_parallelism) is not int
        or int(observed_parallelism) < 1
        or int(observed_parallelism) > 2
    ):
        raise TournamentV2Error("native DAG parallelism evidence is invalid")
    overlap_observed = int(observed_parallelism) >= 2
    supplied_overlap = receipt.get("ready_set_overlap")
    overlap_events = (
        supplied_overlap.get("events")
        if isinstance(supplied_overlap, Mapping)
        else None
    )
    if not isinstance(overlap_events, list) or len(overlap_events) > 4:
        raise TournamentV2Error("native DAG overlap trace is invalid")
    observed_pairs: list[tuple[str, str]] = []
    for sequence, event in enumerate(overlap_events, start=1):
        if (
            not isinstance(event, Mapping)
            or set(event) != {"sequence", "role", "event", "recorded_at"}
            or event.get("sequence") != sequence
            or event.get("role") not in {"integrator", "steward"}
            or event.get("event") not in {"arrived", "released"}
        ):
            raise TournamentV2Error("native DAG overlap trace entry is invalid")
        v1._parse_canonical_utc_timestamp(
            event.get("recorded_at"), label="native overlap recorded_at"
        )
        observed_pairs.append((str(event["role"]), str(event["event"])))
    trace_proves_overlap = len(observed_pairs) == 4 and (
        {pair for pair in observed_pairs[:2]}
        == {("integrator", "arrived"), ("steward", "arrived")}
        and {pair for pair in observed_pairs[2:]}
        == {("integrator", "released"), ("steward", "released")}
    )
    if overlap_observed is not trace_proves_overlap:
        raise TournamentV2Error("native DAG trace does not prove ready-set overlap")
    expected_overlap = {
        "nodes": [integrator.node_id, steward.node_id],
        "shared_dependencies": list(integrator.dependencies),
        "eligible": True,
        "observed": overlap_observed,
        "coordination": "two-party-start-barrier-before-native-handler",
        "events": overlap_events,
        "assurance": "generation-time local observation; offline verifier checks its internal ordering",
    }
    expected_roles = sorted(TOURNAMENT_ROLES)
    expected_symbols = {
        row.role: row.invoked_symbol
        for row in sorted(restored, key=lambda item: item.role)
    }
    expected_executors = {
        row.role: row.executor_id
        for row in sorted(restored, key=lambda item: item.role)
    }
    expected_artifact_files: set[str] = set()
    for row in restored:
        if row.artifact_digest is None:
            continue
        artifact_hex = row.artifact_digest.removeprefix("sha256:")
        expected_artifact_files.add(
            f"evidence/artifacts/sha256/{artifact_hex[:2]}/{artifact_hex}.json"
        )
    expected_artifact_directories: set[str] = set()
    for relative in expected_artifact_files:
        parent = Path(relative).parent
        while parent != Path("."):
            expected_artifact_directories.add(parent.as_posix())
            parent = parent.parent
    native_tree = _manifest(run_root / "native-dag", exclude_root_manifest=False)
    actual_artifact_files = {str(row["path"]) for row in native_tree["files"]}
    if (
        actual_artifact_files != expected_artifact_files
        or set(native_tree["directories"]) != expected_artifact_directories
    ):
        raise TournamentV2Error(
            "native DAG artifact store contains missing or extra entries"
        )
    limitations = [
        "native handlers are deterministic local implementations, not live providers",
        "the in-process boundary is cooperative and is not an OS sandbox",
        "the trial uses the committed clean snapshot and performs no production effect",
        "offline verification checks native artifacts and receipts but does not re-execute the eight handlers",
    ]
    if (
        receipt.get("logical_digest") != expected_logical
        or receipt.get("ready_set_overlap") != expected_overlap
        or receipt.get("native_roles") != expected_roles
        or receipt.get("native_symbols") != expected_symbols
        or receipt.get("executor_ids") != expected_executors
        or receipt.get("semantic_outcomes") != _native_semantic_outcomes(payloads)
        or receipt.get("limitations") != limitations
    ):
        raise TournamentV2Error("native DAG aggregate evidence is not derivable")
    command = receipt.get("test_receipt")
    if not isinstance(command, Mapping) or transcript is None:
        raise TournamentV2Error("native DAG focused tests lack command evidence")
    v1._validate_command_receipt(
        command,
        v1._unittest_command(_NATIVE_DAG_TEST_MODULES),
        transcript,
        repository,
        require_tests=True,
        label="native-dag",
    )
    exact_native = all(
        row.status is NodeStatus.SUCCEEDED
        and row.native_evidence
        and row.invoked_symbol == by_node[row.node_id].native_symbol
        for row in restored
    )
    qualified = (
        command.get("status") == "passed"
        and bool(command.get("tests_run"))
        and exact_native
        and overlap_observed
    )
    if (
        receipt.get("test_modules") != list(_NATIVE_DAG_TEST_MODULES)
        or receipt.get("status") != ("passed" if qualified else "failed")
        or receipt.get("critical") is not (not qualified)
    ):
        raise TournamentV2Error("native DAG status is not derivable")


def _validate_challenger(
    receipt: Mapping[str, Any],
    repository: Path,
    run_root: Path,
    receipts: Mapping[str, Mapping[str, Any]],
    *,
    authority_manifest: str | Path | None,
    authority_digest: str | None,
) -> None:
    if _validate_generic_failure("CHALLENGER-G1", receipt):
        if (run_root / "challenger").exists():
            raise TournamentV2Error("failed challenger retained untyped artifacts")
        return
    _self_digest(receipt, "receipt_digest")
    if receipt.get("status") == "deferred":
        expected = _authority_challenger(
            repository,
            run_root,
            {},
            authority_path=None,
            authority_digest=None,
        )
        if receipt != expected:
            raise TournamentV2Error("deferred challenger receipt is invalid")
        if authority_manifest is not None or authority_digest is not None:
            raise TournamentV2Error("verifier authority does not match deferred run")
        if (run_root / "challenger").exists():
            raise TournamentV2Error("deferred challenger contains unexpected artifacts")
        return
    if receipt.get("status") != "retest-required":
        raise TournamentV2Error("challenger status is invalid")
    if authority_manifest is None or authority_digest is None:
        raise TournamentV2Error(
            "verifying an authority-bound run requires the external path and digest"
        )
    expected_fields = {
        "lane",
        "status",
        "critical",
        "authority_supplied",
        "authority_manifest_path",
        "authority_manifest_sha256",
        "authority_manifest_digest",
        "authenticated_at",
        "repository_head",
        "repository_tree",
        "selected_role",
        "finding",
        "proposal_digest",
        "hypothesis_id",
        "generation",
        "parent_champion_digest",
        "candidate_materialized",
        "evaluation_started",
        "disposition",
        "missing_evidence_obligations",
        "reentry_api",
        "retained_proposal_records",
        "champion_pointer_unchanged",
        "promotion_authorized",
        "operationally_qualified",
        "qualification",
        "receipt_digest",
    }
    if set(receipt) != expected_fields:
        raise TournamentV2Error("authority-bound challenger fields are invalid")
    source = Path(authority_manifest).absolute().resolve(strict=True)
    scan = receipts.get("SCAN-REPOSITORY")
    inventory = scan.get("inventory") if isinstance(scan, Mapping) else None
    if not isinstance(inventory, Mapping):
        raise TournamentV2Error(
            "evaluation authority externality requires the sealed repository inventory"
        )
    source = v1._validate_path_outside_authority(
        source,
        v1._source_authority_roots(repository, inventory),
        label="evaluation authority manifest",
    )
    if (
        str(source) != receipt.get("authority_manifest_path")
        or authority_digest != receipt.get("authority_manifest_digest")
        or _sha256_file(source) != receipt.get("authority_manifest_sha256")
        or receipt.get("authority_supplied") is not True
        or receipt.get("generation") != 1
        or receipt.get("candidate_materialized") is not False
        or receipt.get("evaluation_started") is not False
        or receipt.get("disposition") != "defer"
        or receipt.get("promotion_authorized") is not False
        or receipt.get("operationally_qualified") is not False
    ):
        raise TournamentV2Error("authority-bound challenger is inconsistent")
    manifest: EvaluationAuthorityManifest = load_evaluation_authority_manifest(
        source,
        expected_digest=authority_digest,
        repository_root=repository,
        candidate_root=run_root / "challenger" / "registry",
        run_root=run_root / "challenger",
        as_of=str(receipt["authenticated_at"]),
    )
    if (
        manifest.repository_head != receipt.get("repository_head")
        or manifest.repository_tree != receipt.get("repository_tree")
        or manifest.champion_digest(str(receipt["selected_role"]))
        != receipt.get("parent_champion_digest")
    ):
        raise TournamentV2Error("challenger receipt differs from external authority")
    grades = [receipts[_role_node(role)] for role in TOURNAMENT_ROLES]
    if any(type(grade.get("score")) is not int for grade in grades):
        raise TournamentV2Error("challenger selection lacks complete role grades")
    selected = min(
        grades,
        key=lambda item: (
            int(item["score"]),
            TOURNAMENT_ROLES.index(str(item["role"])),
        ),
    )
    expected_obligations = [
        "evaluator-owned SealedHoldout with an intact pre-build prediction seal",
        "ArtifactStore-backed BoundSurfaceEvidence for held-out, PIT, adversarial, and pinned-comparator surfaces",
        "independent qualification receipts and issuer authority",
        "a genuine RETEST or DEFER outcome before generation-2 re-entry",
    ]
    if (
        receipt.get("selected_role") != selected.get("role")
        or receipt.get("missing_evidence_obligations") != expected_obligations
        or receipt.get("reentry_api")
        != "V2ChallengerRuntime.seal_evaluation -> materialize -> evaluate -> reenter"
        or receipt.get("champion_pointer_unchanged") is not True
    ):
        raise TournamentV2Error("challenger selection or re-entry boundary is invalid")
    finding_document = receipt.get("finding")
    if not isinstance(finding_document, Mapping):
        raise TournamentV2Error("challenger finding is invalid")
    expected_finding = ChallengerFinding(
        finding_id=f"finding:tournament-v2:{selected['role']}",
        role=str(selected["role"]),
        source_episode_id=(
            "episode:tournament-v2:"
            + str(receipts["SCAN-REPOSITORY"]["receipt_digest"])[7:23]
        ),
        summary=(
            f"{selected['role']} remains structurally graded but not operationally qualified"
        ),
        error_class="structural_evidence_only",
        proposed_change=(
            "require evaluator-owned held-out, PIT, adversarial, and comparator evidence"
        ),
        falsifier=(
            "the candidate fails any sealed hard guardrail or cannot beat pinned comparators"
        ),
        evidence_refs=(
            f"role-grade:{selected['grade_digest']}",
            f"code-qa:{receipts['SYSTEM-CODE-QA-V2']['receipt_digest']}",
        ),
        owner_id=manifest.identities.proposer_id,
        expires_at=manifest.expires_at,
    )
    expected_finding_document = json.loads(
        canonical_bytes(asdict(expected_finding)).decode("utf-8")
    )
    if dict(finding_document) != expected_finding_document:
        raise TournamentV2Error("challenger finding is not source-derived")
    retained = receipt.get("retained_proposal_records")
    if not isinstance(retained, list) or len(retained) != 1:
        raise TournamentV2Error("challenger retained proposal evidence is invalid")
    hypothesis_seed = {
        "finding_id": expected_finding.finding_id,
        "role": expected_finding.role,
        "owner_id": expected_finding.owner_id,
        "statement": (
            f"For {expected_finding.role}, {expected_finding.proposed_change}; "
            f"expected effect: reduce {expected_finding.error_class}."
        ),
        "falsifier": expected_finding.falsifier,
        "parent_champion_digest": manifest.champion_digest(expected_finding.role),
        "evidence_refs": list(expected_finding.evidence_refs),
        "generation": 1,
        "prior_outcome_digest": None,
    }
    hypothesis_id = "HYP-" + canonical_digest(hypothesis_seed)[7:23]
    hypothesis_document = {"hypothesis_id": hypothesis_id, **hypothesis_seed}
    lesson_document = {
        "lesson_id": (
            f"{expected_finding.finding_id}-g1-{hypothesis_id.removeprefix('HYP-')[:8]}"
        ),
        "source_episode_id": expected_finding.source_episode_id,
        "outcome": "failure",
        "error_class": expected_finding.error_class,
        "applicability": [f"prompt:{expected_finding.role}"],
        "confidence": 1.0,
        "provenance": list(expected_finding.evidence_refs),
        "expires_at": expected_finding.expires_at,
        "status": "accepted",
    }
    proposal_document: dict[str, Any] = {
        "hypothesis": hypothesis_document,
        "lesson": lesson_document,
    }
    proposal_document["proposal_digest"] = canonical_digest(proposal_document)
    proposal_record = {
        "schema_version": 1,
        "kind": "proposal",
        "authority_manifest_digest": manifest.manifest_digest,
        "proposal": proposal_document,
        "created_at": receipt.get("authenticated_at"),
    }
    proposal_record_digest = canonical_digest(proposal_record)
    expected_relative = (
        "challenger/challenger-authority/proposal/"
        + proposal_record_digest[7:]
        + ".json"
    )
    row = retained[0]
    if (
        not isinstance(row, Mapping)
        or set(row) != {"path", "sha256"}
        or row.get("path") != expected_relative
    ):
        raise TournamentV2Error("challenger retained proposal row is invalid")
    path = run_root / expected_relative
    expected_record_bytes = canonical_bytes(proposal_record) + b"\n"
    if (
        not path.is_file()
        or path.read_bytes() != expected_record_bytes
        or _sha256_file(path) != row.get("sha256")
        or receipt.get("proposal_digest") != proposal_document["proposal_digest"]
        or receipt.get("hypothesis_id") != hypothesis_id
    ):
        raise TournamentV2Error("challenger proposal record is not derivable")
    forbidden_record_roots = (
        "evaluation-plan",
        "materialization",
        "outcome",
        "appeal",
    )
    if any(
        (run_root / "challenger" / "challenger-authority" / name).exists()
        for name in forbidden_record_roots
    ):
        raise TournamentV2Error("manifest-only challenger crossed its DEFER boundary")
    pointer = _strict_json(run_root / "challenger" / "registry" / "champions.json")
    if (
        set(pointer) != {"schema_version", "champions"}
        or pointer.get("schema_version") != 1
        or pointer.get("champions") != manifest.champions
    ):
        raise TournamentV2Error("challenger champion pointer differs from authority")
    expected_pointer_bytes = (
        json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if (
        run_root / "challenger" / "registry" / "champions.json"
    ).read_bytes() != expected_pointer_bytes:
        raise TournamentV2Error("challenger champion pointer is not canonical")

    challenger_root = run_root / "challenger"
    expected_root_directories = {
        "challenger-authority",
        "generation-zero",
        "registry",
    }
    if {
        path.name for path in challenger_root.iterdir() if path.is_dir()
    } != expected_root_directories or any(
        path.is_file() for path in challenger_root.iterdir()
    ):
        raise TournamentV2Error("challenger root contains missing or extra entries")
    generation_root = challenger_root / "generation-zero"
    generation_entries = list(generation_root.iterdir())
    expected_generation_files = {f"{role.value}.txt" for role in Role}
    if {path.name for path in generation_entries} != expected_generation_files or any(
        not path.is_file() for path in generation_entries
    ):
        raise TournamentV2Error(
            "generation-zero inventory is incomplete or contains extras"
        )
    registry_root = challenger_root / "registry"
    registry_directories = {"artifacts", "events", "lineage"}
    registry_files = {".prompt-pointer.lock", "champions.json", "prompt-ledger.sqlite3"}
    registry_entries = list(registry_root.iterdir())
    if {
        path.name for path in registry_entries if path.is_dir()
    } != registry_directories or {
        path.name for path in registry_entries if path.is_file()
    } != registry_files:
        raise TournamentV2Error("challenger registry contains missing or extra entries")
    if (registry_root / ".prompt-pointer.lock").read_bytes() != b"\0" or (
        registry_root / "prompt-ledger.sqlite3"
    ).stat().st_size <= 0:
        raise TournamentV2Error("challenger registry control files are invalid")
    artifact_root = registry_root / "artifacts"
    expected_artifact_names: set[str] = set()
    for role in Role:
        generated = generation_zero_prompt(ROLE_CONTRACTS[role])
        generated_path = generation_root / f"{role.value}.txt"
        if generated_path.read_bytes() != generated.encode("utf-8"):
            raise TournamentV2Error("generation-zero prompt differs from role contract")
        digest = prompt_digest(generated)
        if digest != manifest.champion_digest(role):
            raise TournamentV2Error(
                "generation-zero prompt differs from authority champion"
            )
        artifact_name = digest[7:] + ".prompt"
        expected_artifact_names.add(artifact_name)
        if (artifact_root / artifact_name).read_bytes() != generated.encode("utf-8"):
            raise TournamentV2Error("challenger prompt artifact content is invalid")
    artifact_entries = list(artifact_root.iterdir())
    if (
        {path.name for path in artifact_entries} != expected_artifact_names
        or any(not path.is_file() for path in artifact_entries)
        or any((registry_root / "events").iterdir())
    ):
        raise TournamentV2Error("challenger prompt artifact inventory is invalid")
    lineage_entries = list((registry_root / "lineage").iterdir())
    if len(lineage_entries) != len(Role) * 2 or any(
        not path.is_file() or path.suffix != ".json" for path in lineage_entries
    ):
        raise TournamentV2Error("challenger generation-zero lineage is incomplete")
    lineage_by_role: dict[str, list[Mapping[str, Any]]] = {
        role.value: [] for role in Role
    }
    lineage_documents: list[Mapping[str, Any]] = []
    for lineage_path in lineage_entries:
        try:
            if str(UUID(lineage_path.stem)) != lineage_path.stem:
                raise ValueError("noncanonical UUID")
        except ValueError as error:
            raise TournamentV2Error("challenger lineage filename is invalid") from error
        lineage = _strict_json(lineage_path)
        if lineage_path.read_bytes() != (
            json.dumps(lineage, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8"):
            raise TournamentV2Error("challenger lineage record is not canonical")
        role_name = lineage.get("role")
        if not isinstance(role_name, str) or role_name not in lineage_by_role:
            raise TournamentV2Error("challenger lineage role is invalid")
        _utc_moment(lineage.get("created_at"), label="challenger lineage created_at")
        lineage_by_role[role_name].append(lineage)
        lineage_documents.append(lineage)
    for role_name, rows in lineage_by_role.items():
        digest = manifest.champion_digest(role_name)
        expected_common = {
            "schema_version": 1,
            "role": role_name,
            "artifact_digest": digest,
            "parent_digest": None,
            "created_by": "repository:generation-0",
        }
        if len(rows) != 2:
            raise TournamentV2Error("challenger lineage cardinality is invalid")
        registration = next(
            (value for value in rows if value.get("kind") == "registration"), None
        )
        promotion = next(
            (value for value in rows if value.get("kind") == "promotion"), None
        )
        if (
            not isinstance(registration, Mapping)
            or not isinstance(promotion, Mapping)
            or {key: registration.get(key) for key in expected_common}
            != expected_common
            or set(registration)
            != {*expected_common, "created_at", "experiment_id", "kind"}
            or registration.get("experiment_id") is not None
            or {key: promotion.get(key) for key in expected_common} != expected_common
            or set(promotion)
            != {
                *expected_common,
                "created_at",
                "experiment_id",
                "kind",
                "decision_event_sequence",
                "rollback_digest",
            }
            or promotion.get("experiment_id") != "generation-0"
            or promotion.get("decision_event_sequence") is not None
            or promotion.get("rollback_digest") is not None
        ):
            raise TournamentV2Error("challenger lineage is not generation-zero derived")

    ledger_path = registry_root / "prompt-ledger.sqlite3"
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(
            ledger_path.as_uri() + "?mode=ro&immutable=1", uri=True
        )
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity != ("ok",):
            raise TournamentV2Error("challenger ledger failed SQLite integrity")
        schema = {
            (str(row[0]), str(row[1]))
            for row in connection.execute(
                "SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        expected_schema = {
            ("table", "events"),
            ("table", "lessons"),
            ("trigger", "events_no_update"),
            ("trigger", "events_no_delete"),
            ("trigger", "lessons_no_update"),
            ("trigger", "lessons_no_delete"),
        }
        if schema != expected_schema:
            raise TournamentV2Error("challenger ledger schema is invalid")
        event_rows = connection.execute(
            "SELECT sequence,run_id,event_type,actor,payload,created_at,"
            "prev_digest,row_digest FROM events ORDER BY sequence"
        ).fetchall()
        if len(event_rows) != len(Role) * 2 or connection.execute(
            "SELECT COUNT(*) FROM lessons"
        ).fetchone() != (0,):
            raise TournamentV2Error("challenger ledger event inventory is invalid")
        unmatched = list(lineage_documents)
        previous_digest = ""
        for expected_sequence, event_row in enumerate(event_rows, start=1):
            (
                sequence,
                run_id,
                event_type,
                actor,
                encoded_payload,
                created_at,
                predecessor,
                row_digest,
            ) = event_row
            try:
                payload = json.loads(
                    str(encoded_payload),
                    object_pairs_hook=v1._reject_duplicate_object_pairs,
                    parse_constant=_reject_json_constant,
                )
            except (json.JSONDecodeError, ValueError) as error:
                raise TournamentV2Error(
                    "challenger ledger payload is invalid"
                ) from error
            if not isinstance(payload, Mapping):
                raise TournamentV2Error("challenger ledger payload is not an object")
            canonical_payload = json.dumps(
                payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            material = json.dumps(
                (
                    expected_sequence,
                    str(run_id),
                    str(event_type),
                    str(actor),
                    canonical_payload,
                    str(created_at),
                    previous_digest,
                ),
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            expected_row_digest = f"sha256:{sha256(material).hexdigest()}"
            if (
                sequence != expected_sequence
                or encoded_payload != canonical_payload
                or actor != "repository:generation-0"
                or predecessor != previous_digest
                or row_digest != expected_row_digest
            ):
                raise TournamentV2Error("challenger ledger chain is invalid")
            _utc_moment(created_at, label="challenger ledger created_at")
            role_name = str(payload.get("role"))
            expected_role_name = tuple(Role)[(expected_sequence - 1) // 2].value
            if role_name != expected_role_name:
                raise TournamentV2Error("challenger ledger role ordering is invalid")
            if expected_sequence % 2:
                expected_event = (f"prompt:{role_name}", "prompt.registered")
            else:
                expected_event = ("generation-0", "prompt.promoted")
            if (run_id, event_type) != expected_event:
                raise TournamentV2Error("challenger ledger event ordering is invalid")
            match = next((value for value in unmatched if value == payload), None)
            if match is None:
                raise TournamentV2Error("challenger ledger is not lineage-bound")
            unmatched.remove(match)
            previous_digest = str(row_digest)
        if unmatched:
            raise TournamentV2Error("challenger ledger omits lineage records")
    except sqlite3.DatabaseError as error:
        raise TournamentV2Error(
            "challenger ledger is not a valid SQLite store"
        ) from error
    finally:
        if connection is not None:
            connection.close()

    authority_root = challenger_root / "challenger-authority"
    if {path.name for path in authority_root.iterdir()} != {"proposal"} or not (
        authority_root / "proposal"
    ).is_dir():
        raise TournamentV2Error("challenger authority inventory contains extras")
    proposal_entries = list((authority_root / "proposal").iterdir())
    if proposal_entries != [path]:
        raise TournamentV2Error("challenger proposal inventory is not exact")

    expected_receipt: dict[str, Any] = {
        "lane": "challenger-g1",
        "status": "retest-required",
        "critical": False,
        "authority_supplied": True,
        "authority_manifest_path": str(source),
        "authority_manifest_sha256": _sha256_file(source),
        "authority_manifest_digest": manifest.manifest_digest,
        "authenticated_at": receipt.get("authenticated_at"),
        "repository_head": manifest.repository_head,
        "repository_tree": manifest.repository_tree,
        "selected_role": expected_finding.role,
        "finding": expected_finding_document,
        "proposal_digest": proposal_document["proposal_digest"],
        "hypothesis_id": hypothesis_id,
        "generation": 1,
        "parent_champion_digest": manifest.champion_digest(expected_finding.role),
        "candidate_materialized": False,
        "evaluation_started": False,
        "disposition": "defer",
        "missing_evidence_obligations": expected_obligations,
        "reentry_api": (
            "V2ChallengerRuntime.seal_evaluation -> materialize -> evaluate -> reenter"
        ),
        "retained_proposal_records": [dict(row)],
        "champion_pointer_unchanged": True,
        "promotion_authorized": False,
        "operationally_qualified": False,
        "qualification": (
            "authority authenticated and G1 proposal retained; no holdout, surface, "
            "provider, production, or superiority qualification"
        ),
    }
    expected_receipt["receipt_digest"] = canonical_digest(expected_receipt)
    if dict(receipt) != expected_receipt:
        raise TournamentV2Error("authority-bound challenger receipt is not derivable")


def _validate_waves_and_events(
    run_root: Path,
    waves: Sequence[Sequence[str]],
    receipts: Mapping[str, Mapping[str, Any]],
) -> None:
    expected_wave_files = {
        f"wave-{number:02d}.json" for number in range(1, len(waves) + 1)
    }
    wave_root = run_root / "waves"
    wave_entries = list(wave_root.rglob("*"))
    if any(path.is_dir() or path.suffix != ".json" for path in wave_entries):
        raise TournamentV2Error("v2 wave directory contains unsupported entries")
    observed_wave_files = {path.name for path in wave_entries}
    if observed_wave_files != expected_wave_files:
        raise TournamentV2Error("v2 wave evidence is incomplete or contains extras")
    for number, wave in enumerate(waves, start=1):
        record = _strict_json(run_root / "waves" / f"wave-{number:02d}.json")
        if set(record) != {
            "wave",
            "nodes",
            "parallel",
            "workers_used",
            "attempts",
            "observed_peak_concurrency",
            "status",
            "wave_digest",
        }:
            raise TournamentV2Error("wave record fields are invalid")
        _self_digest(record, "wave_digest")
        if (
            record.get("wave") != number
            or record.get("nodes") != list(wave)
            or record.get("status") != "completed"
            or type(record.get("workers_used")) is not int
            or not 1 <= int(record["workers_used"]) <= len(wave)
            or record.get("parallel")
            is not (len(wave) > 1 and int(record["workers_used"]) > 1)
        ):
            raise TournamentV2Error("wave topology evidence is invalid")
        attempts = record.get("attempts")
        if not isinstance(attempts, Mapping) or set(attempts) != set(wave):
            raise TournamentV2Error("wave attempts are invalid")
        for attempt_node, rows in attempts.items():
            if not isinstance(rows, list) or len(rows) != 1:
                raise TournamentV2Error("wave attempt cardinality is invalid")
            row = rows[0]
            if not isinstance(row, Mapping) or set(row) != {
                "attempt",
                "started_at",
                "ended_at",
                "duration_ms",
                "outcome",
            }:
                raise TournamentV2Error("wave attempt fields are invalid")
            if (
                row.get("attempt") != 1
                or type(row.get("duration_ms")) is not int
                or int(row["duration_ms"]) < 0
            ):
                raise TournamentV2Error("wave attempt is invalid")
            started = v1._parse_canonical_utc_timestamp(
                row.get("started_at"), label=f"wave {number} started_at"
            )
            ended = v1._parse_canonical_utc_timestamp(
                row.get("ended_at"), label=f"wave {number} ended_at"
            )
            elapsed_ms = round((ended - started).total_seconds() * 1000)
            expected_outcome = str(receipts[attempt_node].get("status", "completed"))
            if (
                ended < started
                or abs(elapsed_ms - int(row["duration_ms"])) > 1000
                or row.get("outcome") != expected_outcome
            ):
                raise TournamentV2Error("wave timing or outcome is not receipt-derived")
            if (
                attempt_node == "CHALLENGER-G1"
                and receipts[attempt_node].get("status") == "retest-required"
            ):
                authenticated = v1._parse_canonical_utc_timestamp(
                    receipts[attempt_node].get("authenticated_at"),
                    label="challenger authenticated_at",
                )
                if not started <= authenticated <= ended:
                    raise TournamentV2Error(
                        "challenger authority time is outside its execution attempt"
                    )
            if attempt_node == "SYSTEM-NATIVE-DAG":
                overlap = receipts[attempt_node].get("ready_set_overlap")
                raw_overlap_events = (
                    overlap.get("events") if isinstance(overlap, Mapping) else ()
                )
                overlap_events = (
                    raw_overlap_events if isinstance(raw_overlap_events, list) else []
                )
                moments = [
                    v1._parse_canonical_utc_timestamp(
                        event.get("recorded_at"),
                        label="native overlap recorded_at",
                    )
                    for event in overlap_events
                    if isinstance(event, Mapping)
                ]
                if moments != sorted(moments) or any(
                    moment < started or moment > ended for moment in moments
                ):
                    raise TournamentV2Error(
                        "native overlap trace is outside its execution attempt"
                    )
        observed_peak = _observed_peak(attempts)
        if record.get(
            "observed_peak_concurrency"
        ) != observed_peak or observed_peak > int(record["workers_used"]):
            raise TournamentV2Error("wave concurrency is not derivable")
        if record.get("parallel") is True and observed_peak < 2:
            raise TournamentV2Error("declared parallel wave lacks observed overlap")

    try:
        lines = (run_root / "events.jsonl").read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise TournamentV2Error("v2 event chain is unavailable") from error
    expected_nodes = [node_id for wave in waves for node_id in wave]
    if len(lines) != len(expected_nodes):
        raise TournamentV2Error("v2 event chain length is invalid")
    previous: str | None = None
    for sequence, (line, node_id) in enumerate(zip(lines, expected_nodes), start=1):
        try:
            event = json.loads(
                line, object_pairs_hook=v1._reject_duplicate_object_pairs
            )
        except (json.JSONDecodeError, ValueError) as error:
            raise TournamentV2Error("v2 event chain is invalid JSON") from error
        if not isinstance(event, Mapping) or set(event) != {
            "sequence",
            "node_id",
            "status",
            "receipt_digest",
            "previous_event_digest",
            "event_digest",
        }:
            raise TournamentV2Error("v2 event fields are invalid")
        material = dict(event)
        supplied = material.pop("event_digest")
        if (
            event.get("sequence") != sequence
            or event.get("node_id") != node_id
            or event.get("status") != "completed"
            or event.get("receipt_digest") != _receipt_digest(receipts[node_id])
            or event.get("previous_event_digest") != previous
            or supplied != canonical_digest(material)
        ):
            raise TournamentV2Error("v2 event chain is not derivable")
        previous = str(supplied)


def verify_run_directory_v2(
    run_directory: str | Path,
    *,
    repository: str | Path,
    authority_manifest: str | Path | None = None,
    authority_digest: str | None = None,
) -> dict[str, Any]:
    """Re-derive every v2 bundle hash, schema, gate, and source binding."""

    if (authority_manifest is None) != (authority_digest is None):
        raise TournamentV2Error(
            "authority manifest and caller-expected digest must be supplied together"
        )
    raw_root = Path(run_directory).absolute()
    if v1._has_link_like_component(Path(raw_root.anchor), raw_root):
        raise TournamentV2Error("v2 run path contains a link or junction")
    run_root = raw_root.resolve(strict=True)
    repository_root = Path(repository).resolve(strict=True)
    if (
        Path(__file__).resolve().parent
        != (repository_root / "src/hive_mind_os").resolve()
    ):
        raise TournamentV2Error(
            "v2 verifier was not imported from the selected repository"
        )
    _require_disjoint_roots(
        repository_root, run_root, label="v2 tournament run directory"
    )
    live_inventory = v1.inventory_repository(repository_root)
    v1._validate_path_outside_authority(
        run_root,
        v1._source_authority_roots(repository_root, live_inventory),
        label="v2 tournament run directory",
    )
    manifest = _validate_manifest(run_root)
    plan = _strict_json(run_root / "plan.json")
    waves = validate_tournament_plan_v2(plan)
    expected_nodes = [node_id for wave in waves for node_id in wave]
    expected_receipts = {f"{node_id}.json" for node_id in expected_nodes}
    receipt_root = run_root / "receipts"
    receipt_entries = list(receipt_root.rglob("*"))
    if any(path.is_dir() or path.suffix != ".json" for path in receipt_entries):
        raise TournamentV2Error("v2 receipt directory contains unsupported entries")
    observed_receipts = {path.name for path in receipt_entries}
    if observed_receipts != expected_receipts:
        raise TournamentV2Error("v2 receipts are incomplete or contain extras")
    receipts = {
        node_id: _strict_json(run_root / "receipts" / f"{node_id}.json")
        for node_id in expected_nodes
    }
    scan = receipts["SCAN-REPOSITORY"]
    inventory = _validate_scan(scan, repository_root)

    transcript_root = run_root / "transcripts"
    transcript_entries = list(transcript_root.rglob("*"))
    if any(path.is_dir() or path.suffix != ".txt" for path in transcript_entries):
        raise TournamentV2Error("v2 transcript directory contains unsupported entries")
    transcripts = {path.stem: path for path in transcript_entries}
    consumed_transcripts: set[str] = set()
    for role in TOURNAMENT_ROLES:
        node_id = _role_node(role)
        grade = receipts[node_id]
        if _validate_generic_failure(node_id, grade):
            continue
        transcript_path = transcripts.get(node_id)
        if transcript_path is None:
            raise TournamentV2Error(f"{node_id} transcript is missing")
        transcript = transcript_path.read_text(encoding="utf-8")
        consumed_transcripts.add(node_id)
        v1._validate_role_grade(role, grade, transcript, inventory)
        _self_digest(grade, "grade_digest")

    for node_id in _LEGACY_SYSTEM_NODES:
        receipt = receipts[node_id]
        if _validate_generic_failure(node_id, receipt):
            continue
        transcript_path = transcripts.get(node_id)
        transcript: str | None = None
        if transcript_path is not None:
            transcript = transcript_path.read_text(encoding="utf-8")
            consumed_transcripts.add(node_id)
        v1._validate_system_receipt(node_id, receipt, inventory, transcript)
        _self_digest(receipt, "receipt_digest")
    native_transcript_path = transcripts.get("SYSTEM-NATIVE-DAG")
    native_transcript: str | None = None
    if native_transcript_path is not None:
        native_transcript = native_transcript_path.read_text(encoding="utf-8")
        consumed_transcripts.add("SYSTEM-NATIVE-DAG")
    _validate_native_dag(
        receipts["SYSTEM-NATIVE-DAG"],
        repository_root,
        run_root,
        scan,
        native_transcript,
    )
    _validate_code_qa(receipts["SYSTEM-CODE-QA-V2"], repository_root, run_root)
    _validate_challenger(
        receipts["CHALLENGER-G1"],
        repository_root,
        run_root,
        receipts,
        authority_manifest=authority_manifest,
        authority_digest=authority_digest,
    )
    if set(transcripts) != consumed_transcripts:
        raise TournamentV2Error("v2 transcript directory contains unexpected evidence")

    cross_receipt = receipts["CROSS-EXAMINE"]
    if not _validate_generic_failure("CROSS-EXAMINE", cross_receipt):
        expected_cross = _cross_examine_v2(repository_root, receipts)
        if cross_receipt != expected_cross:
            raise TournamentV2Error("cross-examination is not derivable")
    for role in TOURNAMENT_ROLES:
        feedback_receipt = receipts[_feedback_node(role)]
        if _validate_generic_failure(_feedback_node(role), feedback_receipt):
            continue
        expected_feedback = _feedback_v2(
            role,
            receipts[_role_node(role)],
            receipts["CROSS-EXAMINE"],
            receipts["CHALLENGER-G1"],
        )
        if feedback_receipt != expected_feedback:
            raise TournamentV2Error(f"{role} feedback is not derivable")
    championship = receipts["CHAMPIONSHIP"]
    if _validate_generic_failure("CHAMPIONSHIP", championship):
        expected_report = dict(championship)
    else:
        expected_report = _derive_report(
            receipts,
            plan_digest=str(plan["plan_digest"]),
        )
        if championship != expected_report:
            raise TournamentV2Error("championship receipt is not derivable")
    report = _strict_json(run_root / "report.json")
    if report != expected_report:
        raise TournamentV2Error("v2 report differs from championship receipt")
    try:
        markdown = (run_root / "report.md").read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise TournamentV2Error("v2 Markdown report is unavailable") from error
    if markdown != _render_report(report):
        raise TournamentV2Error("v2 Markdown report is not derivable")
    _validate_waves_and_events(run_root, waves, receipts)

    return {
        "status": "verified",
        "kind": "hive-mind-agent-readiness-tournament-v2-verification",
        "disposition": (
            report["court"]["disposition"]
            if isinstance(report.get("court"), Mapping)
            else "quarantine"
        ),
        "whole_system_grade": report.get("whole_system_grade", "F"),
        "report_digest": _receipt_digest(report),
        "manifest_digest": manifest["manifest_digest"],
        "plan_digest": plan["plan_digest"],
        "repository_head": scan["repository_binding"]["head_commit"],
        "repository_tree": scan["repository_binding"]["tree_oid"],
        "node_count": len(expected_nodes),
        "source_drift": False,
        "promotion_authorized": False,
    }


def _load_plan(path: str | None) -> Mapping[str, Any] | None:
    return None if path is None else _strict_json(Path(path))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the parallel Hive Mind agent-readiness tournament v2"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="write the canonical v2 executable DAG")
    plan.add_argument("--output", required=True)
    run = commands.add_parser("run", help="execute v2 into a new evidence directory")
    run.add_argument("--repository", default=".")
    run.add_argument("--output-dir", required=True)
    run.add_argument("--plan")
    run.add_argument("--max-workers", type=int, default=8)
    run.add_argument("--skip-full-suite", action="store_true")
    run.add_argument("--evaluation-authority-manifest")
    run.add_argument("--evaluation-authority-digest")
    verify = commands.add_parser("verify", help="offline-verify a completed v2 bundle")
    verify.add_argument("--run-dir", required=True)
    verify.add_argument("--repository", default=".")
    verify.add_argument("--evaluation-authority-manifest")
    verify.add_argument("--evaluation-authority-digest")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "plan":
            output = Path(args.output).absolute()
            if os.path.lexists(output):
                raise TournamentV2Error(f"output must not already exist: {output}")
            if not output.parent.is_dir() or v1._has_link_like_component(
                Path(output.anchor), output.parent
            ):
                raise TournamentV2Error(
                    "plan output parent is unavailable or link-like"
                )
            _write_json_create(output, build_tournament_plan_v2())
            result = {
                "status": "planned",
                "path": str(output.resolve()),
                "plan_digest": _strict_json(output)["plan_digest"],
            }
        elif args.command == "run":
            result = run_tournament_v2(
                args.repository,
                args.output_dir,
                max_workers=args.max_workers,
                full_suite=not args.skip_full_suite,
                plan=_load_plan(args.plan),
                authority_manifest=args.evaluation_authority_manifest,
                authority_digest=args.evaluation_authority_digest,
            )
        else:
            result = verify_run_directory_v2(
                args.run_dir,
                repository=args.repository,
                authority_manifest=args.evaluation_authority_manifest,
                authority_digest=args.evaluation_authority_digest,
            )
    except (
        OSError,
        ValueError,
        TournamentV2Error,
        v1.TournamentError,
        json.JSONDecodeError,
    ) as error:
        print(
            json.dumps(
                {"status": "failed", "error": f"{type(error).__name__}: {error}"},
                indent=2,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
