# The tested modules are intentionally imported after the fixture bin path is installed.
# ruff: noqa: E402
from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping
from unittest.mock import patch

BIN = Path(__file__).resolve().parents[1] / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

import controller as controller_module  # noqa: E402
import orchestration as orchestration_module  # noqa: E402
from autopilot import parser as autopilot_parser  # noqa: E402
from autopilot import select_orchestration_status  # noqa: E402
from fixture_support import ready_runtime  # noqa: E402
from orchestration import (  # noqa: E402
    OrchestrationError,
    build_orchestration_contract,
    derive_launch_identity,
    infer_intent,
    should_publish_release,
    simple_prompt,
    validate_policy,
)
from orchestration import (
    assert_launch_authority as _assert_launch_authority_raw,
)
from orchestration import (
    bind_launch as _bind_launch_raw,
)
from orchestration import (
    binding_events as _binding_events_raw,
)
from orchestration import (
    fence_launch as _fence_launch_raw,
)
from orchestration import (
    launch_authority_guard as _launch_authority_guard_raw,
)
from orchestration import (
    launch_binding as _launch_binding_raw,
)
from orchestration import (
    prepare_launch as _prepare_launch_raw,
)
from orchestration import (
    release_terminal_launch as _release_terminal_launch_raw,
)

TEST_REPOSITORY = "test/repo"
TEST_EXECUTION_ID = "sha256:e4721b27bb9e4d6370eb058a64d4d893981cc104a7a6a838f45a564cf0a579ff"
TEST_EXECUTION_NAMESPACE = "default"
TEST_NODE = "ACTIVE-100"
TEST_LIFECYCLE = "NODE_DELIVERY"
TEST_BRANCH = "autopilot/active-100"
TEST_PLAN_MATERIAL = {
    "schema_version": 1,
    "plan_id": "portable-test",
    "title": "Portable orchestration fixture",
    "subject": "Exercise strict execution-scoped launch authority",
    "created_at": "2026-08-14T00:00:00Z",
    "baseline": {"commit": "a" * 40},
    "state_machine": {"initial": "NOT_STARTED", "terminal": ["COMPLETE"]},
    "nodes": [
        {"id": "ACTIVE-100", "branch": "autopilot/active-100"},
        {"id": "CLOSE-200", "branch": "autopilot/close-200"},
        {"id": "NEW-300", "branch": "autopilot/new-300"},
    ],
}
TEST_PLAN_FINGERPRINT = "sha256:" + sha256(
    json.dumps(
        TEST_PLAN_MATERIAL,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()
TEST_METADATA = {
    "target_sha": "a" * 40,
    "plan_fingerprint": TEST_PLAN_FINGERPRINT,
    "target_branch": "release/test",
    "authority_class": "WRITE_AUTHORIZED",
}


def _test_identity(
    *,
    branch: str = TEST_BRANCH,
    attempt: int = 1,
    retry_of: str | None = None,
    authority_class: str = "WRITE_AUTHORIZED",
):
    return derive_launch_identity(
        execution_id=TEST_EXECUTION_ID,
        execution_namespace=TEST_EXECUTION_NAMESPACE,
        repository=TEST_REPOSITORY,
        node_id=TEST_NODE,
        lifecycle=TEST_LIFECYCLE,
        branch=branch,
        target_sha=TEST_METADATA["target_sha"],
        plan_fingerprint=TEST_METADATA["plan_fingerprint"],
        target_branch=TEST_METADATA["target_branch"],
        authority_class=authority_class,
        attempt=attempt,
        retry_of=retry_of,
    )


TEST_RESOURCE = str(_test_identity()["resource_key"])


def _authority_state_dir(root: Path) -> Path | None:
    try:
        coordination = controller_module.resolve_repository_state_dir(root)
    except controller_module.ConfigurationError:
        return None
    if not (coordination / controller_module.RUNTIME_READY_MANIFEST).is_file():
        return None
    ready = controller_module.read_strict_canonical_json(
        coordination / controller_module.RUNTIME_READY_MANIFEST,
        label="test runtime READY",
    )
    if not isinstance(ready, Mapping):
        raise AssertionError("test runtime READY must be an object")
    execution_id = str(ready["default_execution_id"])
    execution_dir = controller_module.execution_namespace_dir(
        coordination, execution_id
    )
    return controller_module.require_execution_authority_dir(
        root,
        execution_dir,
        execution_id=execution_id,
        execution_namespace="default",
    )


@contextlib.contextmanager
def _dispatcher_authority(root: Path, state_dir: Path | None):
    if state_dir is None:
        yield
        return
    with controller_module.runtime_file_lock(
        state_dir / "locks" / "dispatcher-admission.lock",
        timeout_seconds=120.0,
    ):
        yield


def _prepare_launch(root, instruction_id, host, **kwargs):
    state_dir = kwargs.setdefault("state_dir", _authority_state_dir(Path(root)))
    if state_dir is not None:
        identity = controller_module.read_strict_canonical_json(
            state_dir / "execution-identity.json", label="test execution identity"
        )
        kwargs.setdefault("execution_id", str(identity["execution_id"]))
        kwargs.setdefault("execution_namespace", str(identity["namespace"]))
    else:
        # Exercise the production fail-closed path rather than failing Python's
        # call signature before the missing explicit authority is inspected.
        kwargs.setdefault("execution_id", TEST_EXECUTION_ID)
        kwargs.setdefault("execution_namespace", "default")
    authority_class = kwargs.get("authority_class", TEST_METADATA["authority_class"])
    if authority_class == "WRITE_AUTHORIZED":
        kwargs.setdefault("dispatcher_release_id", "sha256:" + "e" * 64)
        kwargs.setdefault("dispatcher_admission_epoch", 1)
    else:
        kwargs.setdefault("dispatcher_release_id", None)
        kwargs.setdefault("dispatcher_admission_epoch", None)
    kwargs.setdefault(
        "host_reservation_id",
        controller_module.digest_json(
            {
                "kind": "hive-mind-test-host-reservation-v1",
                "launch_instruction_id": instruction_id,
            }
        ),
    )
    kwargs.setdefault("capacity_host_id", "test:sealed-host")
    kwargs.setdefault("capacity_generation", "sha256:" + "d" * 64)
    kwargs.setdefault("capacity_epoch", 1)
    kwargs.setdefault("reservation_expires_at", "2099-01-01T00:00:00Z")
    kwargs.setdefault("host_kernel_generation", "sha256:" + "c" * 64)
    adapter_record_id = kwargs.setdefault(
        "execution_adapter_identity_record_id", "sha256:" + "f" * 64
    )
    kwargs.setdefault(
        "execution_adapter_identity_path",
        "execution-adapter-bindings/"
        + str(adapter_record_id).removeprefix("sha256:")
        + ".json",
    )
    kwargs.setdefault(
        "execution_adapter_identity_blob_digest", "sha256:" + "b" * 64
    )
    with _dispatcher_authority(Path(root), state_dir):
        return _prepare_launch_raw(root, instruction_id, host, **kwargs)


def prepare_launch(root, instruction_id, host, **kwargs):
    kwargs.setdefault("repository", TEST_REPOSITORY)
    kwargs.setdefault("node_id", TEST_NODE)
    kwargs.setdefault("lifecycle", TEST_LIFECYCLE)
    kwargs.setdefault("branch", TEST_BRANCH)
    kwargs.setdefault("resource_key", TEST_RESOURCE)
    for field, value in TEST_METADATA.items():
        kwargs.setdefault(field, value)
    return _prepare_launch(root, instruction_id, host, **kwargs)


def launch_binding(root, instruction_id, **kwargs):
    kwargs.setdefault("state_dir", _authority_state_dir(Path(root)))
    return _launch_binding_raw(root, instruction_id, **kwargs)


def binding_events(root, **kwargs):
    kwargs.setdefault("state_dir", _authority_state_dir(Path(root)))
    return _binding_events_raw(root, **kwargs)


def assert_launch_authority(root, instruction_id, **kwargs):
    kwargs.setdefault("state_dir", _authority_state_dir(Path(root)))
    return _assert_launch_authority_raw(root, instruction_id, **kwargs)


@contextlib.contextmanager
def launch_authority_guard(root, instruction_id, **kwargs):
    state_dir = kwargs.setdefault("state_dir", _authority_state_dir(Path(root)))
    # Combined mutation/effect tests must honor the production order:
    # dispatcher authority is outermost to task-binding authority.
    with _dispatcher_authority(Path(root), state_dir):
        with _launch_authority_guard_raw(root, instruction_id, **kwargs) as binding:
            yield binding


def fence_launch(root, instruction_id, **kwargs):
    state_dir = kwargs.setdefault("state_dir", _authority_state_dir(Path(root)))
    with _dispatcher_authority(Path(root), state_dir):
        return _fence_launch_raw(root, instruction_id, **kwargs)


def _current_fence(root: Path, instruction_id: str) -> tuple[str, int]:
    binding = launch_binding(root, instruction_id)
    if binding is None:
        raise AssertionError("test launch has no durable binding")
    return str(binding["resource_key"]), int(binding["authority_epoch"])


def bind_launch(root, instruction_id, host, task_id, **kwargs):
    resource_key, authority_epoch = _current_fence(root, instruction_id)
    kwargs.setdefault("resource_key", resource_key)
    kwargs.setdefault("authority_epoch", authority_epoch)
    return _bind_launch(root, instruction_id, host, task_id, **kwargs)


def _bind_launch(root, instruction_id, host, task_id, **kwargs):
    state_dir = kwargs.setdefault("state_dir", _authority_state_dir(Path(root)))
    with _dispatcher_authority(Path(root), state_dir):
        return _bind_launch_raw(root, instruction_id, host, task_id, **kwargs)


def release_terminal_launch(root, instruction_id, **kwargs):
    resource_key, authority_epoch = _current_fence(root, instruction_id)
    kwargs.setdefault("resource_key", resource_key)
    kwargs.setdefault("authority_epoch", authority_epoch)
    return _release_terminal_launch(root, instruction_id, **kwargs)


def _release_terminal_launch(root, instruction_id, **kwargs):
    state_dir = kwargs.setdefault("state_dir", _authority_state_dir(Path(root)))
    with _dispatcher_authority(Path(root), state_dir):
        return _release_terminal_launch_raw(root, instruction_id, **kwargs)


class FakePlane:
    def __init__(
        self,
        root: Path,
        status: Mapping[str, object],
        nodes: list[Mapping[str, Any]],
    ) -> None:
        self.repo_root = root
        self._status = dict(status)
        self._nodes = nodes
        self.target_branch = str(status.get("target_branch", "release/test"))
        self.expected_plan_fingerprint = str(
            status.get("plan_fingerprint", TEST_PLAN_FINGERPRINT)
        )
        self.control = {"target": {"repository": TEST_REPOSITORY}}
        self.execution_dir = _authority_state_dir(root)
        assert self.execution_dir is not None
        identity = controller_module.read_strict_canonical_json(
            self.execution_dir / "execution-identity.json",
            label="test execution identity",
        )
        assert isinstance(identity, Mapping)
        self.execution_id = str(identity["execution_id"])
        self.execution_namespace = str(identity["namespace"])
        self.authenticated_host_id = "test:sealed-host"

    def status(self) -> Mapping[str, object]:
        return self._status

    def nodes(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(self._nodes)

    def render_worker_prompt(
        self, node_id: str, *, host_id: str | None = None
    ) -> str:
        if host_id != self.authenticated_host_id:
            raise AssertionError("orchestration omitted its authenticated host id")
        return f"canonical worker prompt for {node_id} on {host_id}"

    def current_target_sha(self) -> str:
        return str(self._status.get("target_sha", "a" * 40))


class IntentOrchestrationTests(unittest.TestCase):
    def test_launch_instruction_is_execution_scoped_but_resource_is_shared(self) -> None:
        first = _test_identity()
        second = derive_launch_identity(
            execution_id="sha256:" + "9" * 64,
            execution_namespace="parallel-app",
            repository=TEST_REPOSITORY,
            node_id=TEST_NODE,
            lifecycle=TEST_LIFECYCLE,
            branch=TEST_BRANCH,
            target_sha=TEST_METADATA["target_sha"],
            plan_fingerprint=TEST_METADATA["plan_fingerprint"],
            target_branch=TEST_METADATA["target_branch"],
            authority_class="WRITE_AUTHORIZED",
        )
        self.assertEqual(first["resource_key"], second["resource_key"])
        self.assertNotEqual(
            first["launch_instruction_id"], second["launch_instruction_id"]
        )
        different_node_same_ref = derive_launch_identity(
            execution_id="sha256:" + "8" * 64,
            execution_namespace="other-node",
            repository=TEST_REPOSITORY,
            node_id="OTHER-900",
            lifecycle=TEST_LIFECYCLE,
            branch=TEST_BRANCH,
            target_sha=TEST_METADATA["target_sha"],
            plan_fingerprint=TEST_METADATA["plan_fingerprint"],
            target_branch=TEST_METADATA["target_branch"],
            authority_class="WRITE_AUTHORIZED",
        )
        self.assertEqual(
            first["resource_key"], different_node_same_ref["resource_key"]
        )
        self.assertNotEqual(
            first["launch_instruction_id"],
            different_node_same_ref["launch_instruction_id"],
        )

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / ".autopilot").mkdir()
        source = Path(__file__).resolve().parents[1] / "orchestration-policy.json"
        shutil.copy2(source, self.root / ".autopilot" / "orchestration-policy.json")
        shutil.copy2(
            Path(__file__).resolve().parents[1] / "task-bindings.lock",
            self.root / ".autopilot" / "task-bindings.lock",
        )
        control = json.loads(
            (Path(__file__).resolve().parents[1] / "control-plane.json").read_text(
                encoding="utf-8"
            )
        )
        control["target"]["repository"] = TEST_REPOSITORY
        control["target"]["branch"] = TEST_METADATA["target_branch"]
        control["target"]["baseline_sha"] = TEST_METADATA["target_sha"]
        control["plan_fingerprint"] = TEST_METADATA["plan_fingerprint"]
        control["verify_git_objects"] = False
        controller_module.atomic_write_json(
            self.root / ".autopilot" / "control-plane.json",
            control,
        )
        controller_module.atomic_write_json(
            self.root / ".autopilot" / "plan.json",
            {**TEST_PLAN_MATERIAL, "plan_fingerprint": TEST_PLAN_FINGERPRINT},
        )
        ready_runtime(controller_module, self.root)
        self.nodes = [
            {
                "id": "ACTIVE-100",
                "branch": "autopilot/active-100",
                "pr_target": "release/test",
                "write_scope": ["src/active/**"],
                "critical_path_importance": 50,
                "downstream_unlock_value": 40,
            },
            {
                "id": "CLOSE-200",
                "branch": "autopilot/close-200",
                "pr_target": "release/test",
                "write_scope": ["src/close/**"],
                "critical_path_importance": 90,
                "downstream_unlock_value": 80,
            },
            {
                "id": "NEW-300",
                "branch": "autopilot/new-300",
                "pr_target": "release/test",
                "write_scope": ["src/new/**"],
                "critical_path_importance": 100,
                "downstream_unlock_value": 100,
            },
        ]

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def status(self, rows: list[dict[str, object]]) -> dict[str, object]:
        return {
            "plan_id": "portable-test",
            "plan_fingerprint": TEST_PLAN_FINGERPRINT,
            "target_branch": "release/test",
            "target_sha": "a" * 40,
            "reconciliation_required": False,
            "eligible": [
                str(row["node_id"])
                for row in rows
                if row.get("state") == "READY"
            ],
            "ready": [],
            "dispatch_release": {
                "valid": False,
                "released_wave": [],
                "issues": ["no current dispatcher release"],
            },
            "nodes": rows,
            "complete": False,
            "active_claims": [],
            "active_validation_lease": None,
        }

    def test_explicit_and_implicit_intents(self) -> None:
        self.assertEqual(infer_intent("Finish everything to quiescence", {}).intent, "FINISH")
        self.assertEqual(infer_intent("Pick up where it stopped", {}).intent, "CONTINUE")
        self.assertEqual(infer_intent("What is left?", {}).intent, "CHECK")
        self.assertEqual(infer_intent("Kick off the next wave", {}).intent, "START")
        self.assertEqual(infer_intent("Build an autopilot DAG", None).intent, "BUILD_DAG")
        inferred = infer_intent(
            "Handle the rest",
            self.status([{"node_id": "ACTIVE-100", "state": "RUNNING"}]),
        )
        self.assertEqual(inferred.intent, "CONTINUE")
        self.assertFalse(inferred.explicit)

    def test_negation_advice_and_quoted_text_do_not_authorize_execution(self) -> None:
        cases = (
            "Don't start anything; just summarize the state.",
            "Do not continue this DAG.",
            "Check only; do not build or start anything.",
            "Do nothing.",
            "Don't make any changes.",
            "What would you do next?",
            "Why didn't it start?",
            "Explain how to finish the DAG",
            "How can I finish the DAG?",
            "Review how to start the next level",
            "Should we finish the DAG?",
            "Is it safe to start now?",
            "Could this continue without review?",
            'Explain the README sentence "keep going until done".',
        )
        for request in cases:
            with self.subTest(request=request):
                self.assertEqual(infer_intent(request, {}).intent, "CHECK")

    def test_closure_first_manages_active_recovery_and_read_only_preparation_in_parallel(self) -> None:
        status = self.status(
            [
                {"node_id": "ACTIVE-100", "state": "RUNNING", "reasons": []},
                {"node_id": "CLOSE-200", "state": "CI_FAILED", "reasons": ["CI failed"]},
                {"node_id": "NEW-300", "state": "READY", "reasons": []},
            ]
        )
        plane = FakePlane(self.root, status, self.nodes)
        contract = build_orchestration_contract(plane, "Handle the rest", status=status)
        tasks = {str(item["node_id"]): item for item in contract["tasks"]}
        self.assertEqual(set(tasks), {"ACTIVE-100", "CLOSE-200", "NEW-300"})
        self.assertEqual(tasks["ACTIVE-100"]["action"], "RESUME")
        self.assertEqual(tasks["CLOSE-200"]["action"], "REPAIR_CI")
        self.assertEqual(tasks["NEW-300"]["action"], "PREPARE_READ_ONLY")
        self.assertEqual(tasks["NEW-300"]["authority_mode"], "PREPARATION_ONLY")
        self.assertFalse(tasks["NEW-300"]["may_claim_or_write"])
        self.assertEqual(contract["closure_target"], "CLOSE-200")
        self.assertTrue(
            contract["execution"]["closure_target_prioritizes_collection_not_task_creation"]
        )
        self.assertFalse(should_publish_release(infer_intent("finish", status), status))

    def test_released_parallel_wave_emits_durable_primary_tasks(self) -> None:
        rows = [
            {"node_id": "ACTIVE-100", "state": "READY", "reasons": []},
            {"node_id": "CLOSE-200", "state": "READY", "reasons": []},
        ]
        status = self.status(rows)
        status["dispatch_release"] = {
            "valid": True,
            "released_wave": ["ACTIVE-100", "CLOSE-200"],
            "directive": "START TOGETHER NOW",
        }
        status["ready"] = ["ACTIVE-100", "CLOSE-200"]
        plane = FakePlane(self.root, status, self.nodes)
        contract = build_orchestration_contract(plane, "start", status=status)
        self.assertEqual(len(contract["tasks"]), 2)
        for task in contract["tasks"]:
            self.assertEqual(task["transport"], "durable_user_owned_task")
            self.assertEqual(task["host_adapters"]["codex"]["create"], "create_thread")
            self.assertIn("orchestration-policy.json", task["prompt"])
            self.assertRegex(task["launch_instruction_id"], r"^sha256:[0-9a-f]{64}$")
            self.assertRegex(task["resource_key"], r"^sha256:[0-9a-f]{64}$")
            self.assertIn(task["launch_instruction_id"][7:19], task["title"])
            self.assertEqual(task["target_branch"], "release/test")
            self.assertEqual(task["authority_mode"], "EXECUTION_AUTHORIZED")
            self.assertTrue(task["may_claim_or_write"])
            self.assertEqual(task["target_sha"], status["target_sha"])
            self.assertEqual(task["plan_fingerprint"], status["plan_fingerprint"])
            self.assertEqual(task["authority_class"], "WRITE_AUTHORIZED")
            self.assertIn("<epoch returned by prepare-launch or bind-launch>", task["prompt"])
        self.assertEqual(
            contract["execution"]["executor_module"],
            ".autopilot/bin/host_execution.py",
        )
        self.assertFalse(contract["execution"]["parent_final_while_required_tasks_active"])

    def test_existing_recovery_does_not_suppress_released_or_preparation_tasks(self) -> None:
        rows = [
            {"node_id": "ACTIVE-100", "state": "RUNNING", "reasons": []},
            {"node_id": "CLOSE-200", "state": "READY", "reasons": []},
            {"node_id": "NEW-300", "state": "READY", "reasons": []},
        ]
        status = self.status(rows)
        status["dispatch_release"] = {
            "valid": True,
            "released_wave": ["CLOSE-200"],
            "directive": "START NOW",
        }
        status["ready"] = ["CLOSE-200"]
        plane = FakePlane(self.root, status, self.nodes)

        contract = build_orchestration_contract(plane, "continue", status=status)
        tasks = {str(task["node_id"]): task for task in contract["tasks"]}

        self.assertEqual(set(tasks), {"ACTIVE-100", "CLOSE-200", "NEW-300"})
        self.assertEqual(tasks["ACTIVE-100"]["authority_mode"], "RECOVERY_AUTHORIZED")
        self.assertEqual(tasks["CLOSE-200"]["authority_mode"], "EXECUTION_AUTHORIZED")
        self.assertEqual(tasks["NEW-300"]["authority_mode"], "PREPARATION_ONLY")
        self.assertTrue(tasks["CLOSE-200"]["may_claim_or_write"])
        self.assertFalse(tasks["NEW-300"]["may_claim_or_write"])
        self.assertEqual(len({task["title"] for task in tasks.values()}), 3)
        self.assertEqual(contract["task_cohort"]["size"], 3)
        self.assertEqual(
            contract["task_cohort"]["authority_counts"],
            {
                "EXECUTION_AUTHORIZED": 1,
                "PREPARATION_ONLY": 1,
                "RECOVERY_AUTHORIZED": 1,
            },
        )
        self.assertTrue(contract["task_cohort"]["created_together_before_first_wait"])
        self.assertTrue(contract["task_cohort"]["every_task_polled_to_terminal"])
        for node_id, task in tasks.items():
            self.assertIn(node_id, task["title"])
            self.assertIn(str(task["action"]), task["title"])
            self.assertIn(str(task["authority_mode"]), task["title"])

    def test_total_primary_cohort_is_capped_with_deterministic_preparation_priority(self) -> None:
        nodes = [
            {
                "id": f"NODE-{index:03d}",
                "branch": f"autopilot/node-{index:03d}",
                "pr_target": "release/test",
                "write_scope": [f"src/node-{index:03d}/**"],
                "critical_path_importance": index,
                "downstream_unlock_value": index,
            }
            for index in range(12)
        ]
        rows = [
            {"node_id": str(node["id"]), "state": "READY", "reasons": []}
            for node in nodes
        ]
        status = self.status(rows)
        plane = FakePlane(self.root, status, nodes)

        contract = build_orchestration_contract(plane, "continue", status=status)

        self.assertEqual(contract["task_cohort"]["size"], 8)
        self.assertEqual(contract["task_cohort"]["canonical_cap"], 8)
        self.assertEqual(
            [task["node_id"] for task in contract["tasks"]],
            [f"NODE-{index:03d}" for index in range(11, 3, -1)],
        )
        self.assertTrue(
            all(task["authority_mode"] == "PREPARATION_ONLY" for task in contract["tasks"])
        )
        self.assertEqual(contract["sidecar_cohort"]["size"], 0)

    def test_initial_sidecars_use_only_remaining_total_host_capacity(self) -> None:
        nodes = [
            {
                "id": f"NODE-{index:03d}",
                "branch": f"autopilot/node-{index:03d}",
                "pr_target": "release/test",
                "write_scope": [f"src/node-{index:03d}/**"],
                "read_scope": ["src/**", "tests/**", "docs/**"],
                "risk": "high",
                "critical_path_importance": index,
                "downstream_unlock_value": index,
            }
            for index in range(7)
        ]
        rows = [
            {"node_id": str(node["id"]), "state": "RUNNING", "reasons": []}
            for node in nodes
        ]
        status = self.status(rows)
        plane = FakePlane(self.root, status, nodes)

        first = build_orchestration_contract(plane, "continue", status=status)
        second = build_orchestration_contract(plane, "continue", status=status)

        self.assertEqual(first["task_cohort"]["size"], 7)
        self.assertEqual(first["sidecar_cohort"]["size"], 1)
        self.assertEqual(first["sidecar_cohort"]["canonical_host_cap"], 8)
        self.assertEqual(first["sidecar_cohort"]["initial_host_reservations"], 8)
        self.assertEqual(first["sidecar_cohort"]["remaining_descendant_slots"], 0)
        self.assertEqual(
            len(first["tasks"]) + int(first["sidecar_cohort"]["size"]),
            8,
        )
        self.assertEqual(
            first["sidecar_cohort"]["sidecar_ids"],
            second["sidecar_cohort"]["sidecar_ids"],
        )

    def test_mandatory_primary_overflow_fails_closed(self) -> None:
        nodes = [
            {
                "id": f"NODE-{index:03d}",
                "branch": f"autopilot/node-{index:03d}",
                "pr_target": "release/test",
                "write_scope": [f"src/node-{index:03d}/**"],
                "critical_path_importance": index,
                "downstream_unlock_value": index,
            }
            for index in range(9)
        ]
        rows = [
            {"node_id": str(node["id"]), "state": "RUNNING", "reasons": []}
            for node in nodes
        ]
        status = self.status(rows)
        plane = FakePlane(self.root, status, nodes)

        with self.assertRaisesRegex(
            OrchestrationError, "mandatory primary cohort exceeds canonical cap 8"
        ):
            build_orchestration_contract(plane, "continue", status=status)

    def test_attended_contract_can_truthfully_omit_preparation_tasks(self) -> None:
        rows = [
            {"node_id": "ACTIVE-100", "state": "RUNNING", "reasons": []},
            {"node_id": "NEW-300", "state": "READY", "reasons": []},
        ]
        status = self.status(rows)
        plane = FakePlane(self.root, status, self.nodes)

        contract = build_orchestration_contract(
            plane,
            "continue",
            status=status,
            allow_preparation_tasks=False,
        )

        self.assertEqual([task["node_id"] for task in contract["tasks"]], ["ACTIVE-100"])
        self.assertFalse(
            contract["execution"]["create_eligible_read_only_preparation_tasks"]
        )

    def test_write_authority_atomically_supersedes_active_preparation(self) -> None:
        preparation = derive_launch_identity(
            execution_id=TEST_EXECUTION_ID,
            execution_namespace=TEST_EXECUTION_NAMESPACE,
            repository=TEST_REPOSITORY,
            node_id=TEST_NODE,
            lifecycle=TEST_LIFECYCLE,
            authority_class="PREPARATION_ONLY",
            branch=TEST_BRANCH,
            target_branch=TEST_METADATA["target_branch"],
            target_sha=TEST_METADATA["target_sha"],
            plan_fingerprint=TEST_METADATA["plan_fingerprint"],
        )
        prepared = _prepare_launch(
            self.root,
            str(preparation["launch_instruction_id"]),
            "codex-attended",
            repository=TEST_REPOSITORY,
            node_id=TEST_NODE,
            lifecycle=TEST_LIFECYCLE,
            branch=TEST_BRANCH,
            resource_key=str(preparation["resource_key"]),
            target_sha=TEST_METADATA["target_sha"],
            plan_fingerprint=TEST_METADATA["plan_fingerprint"],
            target_branch=TEST_METADATA["target_branch"],
            authority_class="PREPARATION_ONLY",
        )
        _bind_launch(
            self.root,
            str(preparation["launch_instruction_id"]),
            "codex-attended",
            "attended-preparation",
            host_id="codex-attended",
            cursor="attended-v1",
            capability="durable_user_owned_task",
            resource_key=str(preparation["resource_key"]),
            authority_epoch=int(prepared["authority_epoch"]),
        )

        write = _test_identity()
        successor = prepare_launch(
            self.root,
            str(write["launch_instruction_id"]),
            "codex-attended",
        )

        old = launch_binding(self.root, str(preparation["launch_instruction_id"]))
        self.assertEqual(old["state"], "SUPERSEDED")
        self.assertEqual(old["superseded_by"], write["launch_instruction_id"])
        self.assertEqual(successor["state"], "PREPARED")
        self.assertGreater(successor["authority_epoch"], prepared["authority_epoch"])
        with self.assertRaisesRegex(OrchestrationError, "not in an allowed transition state"):
            assert_launch_authority(
                self.root,
                str(preparation["launch_instruction_id"]),
                resource_key=str(preparation["resource_key"]),
                authority_epoch=int(prepared["authority_epoch"]),
            )

    def test_launch_binding_is_append_only_and_consumed_before_create(self) -> None:
        rows = [{"node_id": "ACTIVE-100", "state": "READY", "reasons": []}]
        status = self.status(rows)
        status["dispatch_release"] = {
            "valid": True,
            "released_wave": ["ACTIVE-100"],
            "directive": "START NOW",
        }
        plane = FakePlane(self.root, status, self.nodes)
        first = build_orchestration_contract(plane, "start", status=status)
        instruction_id = first["tasks"][0]["launch_instruction_id"]
        prepared = prepare_launch(self.root, instruction_id, "codex")
        self.assertEqual(prepared["state"], "PREPARED")
        recovering = build_orchestration_contract(plane, "continue", status=status)
        self.assertEqual(recovering["tasks"][0]["action"], "RECOVER_PREPARED")
        bound = bind_launch(
            self.root,
            instruction_id,
            "codex",
            "thread-123",
            host_id="local",
            cursor="cursor-1",
            capability="capability-1",
        )
        self.assertEqual(bound["state"], "BOUND")
        running_status = self.status(
            [{"node_id": "ACTIVE-100", "state": "RUNNING", "reasons": []}]
        )
        resumed = build_orchestration_contract(
            plane, "continue", status=running_status
        )
        self.assertEqual(
            resumed["tasks"][0]["launch_instruction_id"], instruction_id
        )
        self.assertEqual(resumed["tasks"][0]["action"], "RESUME_BOUND")
        self.assertEqual(resumed["tasks"][0]["binding"]["task_id"], "thread-123")
        self.assertEqual([event["state"] for event in binding_events(self.root)], ["PREPARED", "CREATED", "BOUND"])
        released = release_terminal_launch(
            self.root,
            instruction_id,
            host="codex",
            host_id="local",
            task_id="thread-123",
            cursor="cursor-1",
            capability="capability-1",
            terminal_state="SUCCEEDED",
            host_event_id="terminal-123",
            host_event_cursor="terminal-cursor-123",
        )
        self.assertEqual(released["state"], "RELEASED")
        self.assertEqual(
            [event["state"] for event in binding_events(self.root)],
            ["PREPARED", "CREATED", "BOUND", "RELEASED"],
        )
        for event in binding_events(self.root):
            self.assertEqual(event["resource_key"], TEST_RESOURCE)
            self.assertEqual(event["authority_epoch"], 1)
            for field, value in TEST_METADATA.items():
                self.assertEqual(event[field], value)

    def test_release_launch_requires_terminal_evidence(self) -> None:
        instruction_id = str(_test_identity()["launch_instruction_id"])
        prepare_launch(self.root, instruction_id, "codex")
        bind_launch(
            self.root, instruction_id, "codex", "thread-live",
            host_id="host", cursor="cursor", capability="capability"
        )
        with self.assertRaises(Exception):
            release_terminal_launch(
                self.root,
                instruction_id,
                host="codex",
                host_id="host",
                task_id="thread-live",
                cursor="cursor",
                capability="forged",
                terminal_state="SUCCEEDED",
                host_event_id="forged-terminal",
                host_event_cursor="forged-cursor",
            )
        self.assertEqual(binding_events(self.root)[-1]["state"], "BOUND")

    def test_raw_cli_cannot_assert_terminal_host_evidence(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                autopilot_parser().parse_args(
                    ["--repo-root", str(self.root), "record-launch-terminal"]
                )
            with self.assertRaises(SystemExit):
                autopilot_parser().parse_args(
                    ["--repo-root", str(self.root), "release-launch"]
                )

    def test_worker_cli_cannot_select_privileged_claim_authority(self) -> None:
        base = [
            "--repo-root",
            str(self.root),
            "claim",
            TEST_NODE,
            "--owner",
            "worker:test",
        ]
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                autopilot_parser().parse_args(base)
            with self.assertRaises(SystemExit):
                autopilot_parser().parse_args(
                    [
                        *base,
                        "--launch-instruction-id",
                        str(_test_identity()["launch_instruction_id"]),
                        "--resource-key",
                        TEST_RESOURCE,
                        "--authority-epoch",
                        "1",
                        "--claim-authority-class",
                        "PRIVILEGED_INTERNAL",
                    ]
                )

    def test_successful_release_is_an_idempotency_tombstone(self) -> None:
        instruction_id = str(_test_identity()["launch_instruction_id"])
        prepare_launch(self.root, instruction_id, "codex")
        bind_launch(
            self.root, instruction_id, "codex", "thread-success",
            host_id="host", cursor="cursor", capability="capability"
        )
        released = release_terminal_launch(
            self.root,
            instruction_id,
            host="codex",
            host_id="host",
            task_id="thread-success",
            cursor="cursor",
            capability="capability",
            terminal_state="SUCCEEDED",
            host_event_id="success-terminal",
            host_event_cursor="success-cursor",
        )
        replay = prepare_launch(self.root, instruction_id, "codex")
        self.assertEqual(replay["event_id"], released["event_id"])
        self.assertEqual(len(binding_events(self.root)), 4)

    def test_failed_retry_requires_new_instruction_and_explicit_lineage(self) -> None:
        first_id = str(_test_identity()["launch_instruction_id"])
        prepare_launch(self.root, first_id, "codex")
        bind_launch(
            self.root, first_id, "codex", "thread-failed",
            host_id="host", cursor="cursor", capability="capability"
        )
        released = release_terminal_launch(
            self.root,
            first_id,
            host="codex",
            host_id="host",
            task_id="thread-failed",
            cursor="cursor",
            capability="capability",
            terminal_state="FAILED",
            host_event_id="failed-terminal",
            host_event_cursor="failed-cursor",
        )
        with self.assertRaises(OrchestrationError):
            prepare_launch(self.root, first_id, "codex")
        second_id = str(
            _test_identity(attempt=2, retry_of=str(released["event_id"]))[
                "launch_instruction_id"
            ]
        )
        retry = prepare_launch(
            self.root,
            second_id,
            "codex",
            attempt=2,
            retry_of=str(released["event_id"]),
        )
        self.assertEqual(retry["attempt"], 2)
        self.assertEqual(retry["retry_of"], released["event_id"])

    def test_contract_generates_attempt_specific_retry_lineage(self) -> None:
        rows = [{"node_id": "ACTIVE-100", "state": "READY", "reasons": []}]
        status = self.status(rows)
        status["dispatch_release"] = {"valid": True, "released_wave": ["ACTIVE-100"]}
        plane = FakePlane(self.root, status, self.nodes)
        first = build_orchestration_contract(plane, "start", status=status)["tasks"][0]
        prepare_launch(self.root, first["launch_instruction_id"], "codex")
        bind_launch(
            self.root, first["launch_instruction_id"], "codex", "thread-failed-contract",
            host_id="host", cursor="cursor", capability="capability"
        )
        released = release_terminal_launch(
            self.root,
            first["launch_instruction_id"],
            host="codex",
            host_id="host",
            task_id="thread-failed-contract",
            cursor="cursor",
            capability="capability",
            terminal_state="FAILED",
            host_event_id="contract-failed-terminal",
            host_event_cursor="contract-failed-cursor",
        )
        retry = build_orchestration_contract(plane, "start", status=status)["tasks"][0]
        self.assertNotEqual(first["launch_instruction_id"], retry["launch_instruction_id"])
        self.assertEqual(retry["attempt"], 2)
        self.assertEqual(retry["retry_of"], released["event_id"])
        prepared = prepare_launch(
            self.root,
            retry["launch_instruction_id"],
            "codex",
            attempt=retry["attempt"],
            retry_of=retry["retry_of"],
        )
        self.assertEqual(prepared["attempt"], 2)

    def test_binding_state_symlink_escape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as outside_name:
            state = self.root / ".autopilot" / "state"
            try:
                os.symlink(outside_name, state, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"directory symlinks unavailable: {error}")
            with self.assertRaises(OrchestrationError):
                prepare_launch(
                    self.root,
                    str(_test_identity()["launch_instruction_id"]),
                    "codex",
                )

    def test_prepared_launch_cannot_be_taken_over_by_another_host(self) -> None:
        instruction_id = str(_test_identity()["launch_instruction_id"])
        prepare_launch(self.root, instruction_id, "codex")
        with self.assertRaises(Exception):
            bind_launch(
                self.root, instruction_id, "other-host", "foreign-task",
                capability="foreign-capability"
            )

    def test_concurrent_prepare_launch_is_idempotent_and_hash_chained(self) -> None:
        instruction_id = str(_test_identity()["launch_instruction_id"])
        with ThreadPoolExecutor(max_workers=12) as executor:
            results = list(
                executor.map(
                    lambda _: prepare_launch(self.root, instruction_id, "codex"),
                    range(12),
                )
            )
        self.assertEqual({item["event_id"] for item in results}, {results[0]["event_id"]})
        self.assertEqual(len(binding_events(self.root)), 1)

    def test_exact_resource_epoch_is_required_and_explicit_fence_is_monotonic(self) -> None:
        first_id = str(_test_identity()["launch_instruction_id"])
        first = _prepare_launch(
            self.root,
            first_id,
            "codex",
            repository=TEST_REPOSITORY,
            node_id=TEST_NODE,
            lifecycle=TEST_LIFECYCLE,
            branch=TEST_BRANCH,
            resource_key=TEST_RESOURCE,
            **TEST_METADATA,
        )
        self.assertEqual(first["authority_epoch"], 1)
        with self.assertRaisesRegex(OrchestrationError, "stale resource fence"):
            _bind_launch(
                self.root,
                first_id,
                "codex",
                "thread-stale",
                capability="capability",
                resource_key=TEST_RESOURCE,
                authority_epoch=2,
            )
        bound = _bind_launch(
            self.root,
            first_id,
            "codex",
            "thread-current",
            capability="capability",
            resource_key=TEST_RESOURCE,
            authority_epoch=1,
        )
        self.assertEqual(bound["authority_epoch"], 1)
        fenced = fence_launch(
            self.root,
            first_id,
            actor="curator:test",
            reason="explicit test revocation",
        )
        self.assertEqual(fenced["state"], "SUPERSEDED")
        with self.assertRaises(OrchestrationError):
            assert_launch_authority(
                self.root,
                first_id,
                resource_key=TEST_RESOURCE,
                authority_epoch=1,
            )
        second_authority = "PREPARATION_ONLY"
        second_id = str(
            _test_identity(authority_class=second_authority)["launch_instruction_id"]
        )
        second_metadata = {**TEST_METADATA, "authority_class": second_authority}
        second = _prepare_launch(
            self.root,
            second_id,
            "codex",
            repository=TEST_REPOSITORY,
            node_id=TEST_NODE,
            lifecycle=TEST_LIFECYCLE,
            branch=TEST_BRANCH,
            resource_key=TEST_RESOURCE,
            **second_metadata,
        )
        self.assertEqual(second["authority_epoch"], 2)

    def test_contract_omission_does_not_revoke_an_active_launch(self) -> None:
        instruction_id = str(_test_identity()["launch_instruction_id"])
        prepare_launch(self.root, instruction_id, "codex")
        before = tuple(binding_events(self.root))
        status = self.status([{"node_id": "NEW-300", "state": "READY"}])
        build_orchestration_contract(
            FakePlane(self.root, status, self.nodes),
            "check",
            status=status,
        )
        after = tuple(binding_events(self.root))
        self.assertEqual(after, before)
        self.assertEqual(after[-1]["state"], "PREPARED")

    def test_authority_guard_serializes_explicit_fence_with_short_effect(self) -> None:
        instruction_id = str(_test_identity()["launch_instruction_id"])
        prepared = prepare_launch(self.root, instruction_id, "codex")
        started = threading.Event()
        finished = threading.Event()

        def revoke():
            started.set()
            value = fence_launch(
                self.root,
                instruction_id,
                actor="curator:test",
                reason="serialized after guarded effect",
            )
            finished.set()
            return value

        with ThreadPoolExecutor(max_workers=1) as executor:
            with launch_authority_guard(
                self.root,
                instruction_id,
                resource_key=str(prepared["resource_key"]),
                authority_epoch=int(prepared["authority_epoch"]),
            ):
                future = executor.submit(revoke)
                self.assertTrue(started.wait(1))
                self.assertFalse(finished.wait(0.1))
            self.assertEqual(future.result(timeout=15)["state"], "SUPERSEDED")

    def test_resource_is_stable_when_target_snapshot_changes(self) -> None:
        rows = [{"node_id": "ACTIVE-100", "state": "READY", "reasons": []}]
        first_status = self.status(rows)
        first_status["dispatch_release"] = {
            "valid": True,
            "released_wave": ["ACTIVE-100"],
        }
        second_status = copy.deepcopy(first_status)
        second_status["target_sha"] = "b" * 40
        first = build_orchestration_contract(
            FakePlane(self.root, first_status, self.nodes), "start", status=first_status
        )["tasks"][0]
        second = build_orchestration_contract(
            FakePlane(self.root, second_status, self.nodes), "start", status=second_status
        )["tasks"][0]
        self.assertEqual(first["resource_key"], second["resource_key"])
        self.assertNotEqual(first["launch_instruction_id"], second["launch_instruction_id"])

    def test_prepare_rejects_forged_lifecycle_and_worker_branch(self) -> None:
        for lifecycle, branch, expected in (
            ("FORGED_LIFECYCLE", TEST_BRANCH, "lifecycle"),
            (TEST_LIFECYCLE, "autopilot/forged", "worker branch"),
        ):
            with self.subTest(lifecycle=lifecycle, branch=branch):
                identity = derive_launch_identity(
                    execution_id=TEST_EXECUTION_ID,
                    execution_namespace=TEST_EXECUTION_NAMESPACE,
                    repository=TEST_REPOSITORY,
                    node_id=TEST_NODE,
                    lifecycle=lifecycle,
                    branch=branch,
                    **TEST_METADATA,
                )
                with self.assertRaisesRegex(OrchestrationError, expected):
                    _prepare_launch(
                        self.root,
                        str(identity["launch_instruction_id"]),
                        "codex",
                        repository=TEST_REPOSITORY,
                        node_id=TEST_NODE,
                        lifecycle=lifecycle,
                        branch=branch,
                        resource_key=str(identity["resource_key"]),
                        **TEST_METADATA,
                    )
        self.assertEqual(binding_events(self.root), ())

    def test_incomplete_legacy_binding_schema_is_rejected(self) -> None:
        instruction_id = str(_test_identity()["launch_instruction_id"])
        prepare_launch(self.root, instruction_id, "codex")
        execution_dir = _authority_state_dir(self.root)
        assert execution_dir is not None
        path = execution_dir / "task-bindings.jsonl"
        previous = None
        encoded = []
        for current_id in (instruction_id, "sha256:" + "e" * 64):
            material = {
                "schema_version": 1,
                "launch_instruction_id": current_id,
                "state": "PREPARED",
                "host": "codex",
                "attempt": 1,
                "retry_of": None,
                "previous_event_id": previous,
                "recorded_at": "2026-08-14T00:00:00Z",
            }
            event_id = "sha256:" + sha256(
                json.dumps(
                    material,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            encoded.append(json.dumps({**material, "event_id": event_id}, sort_keys=True))
            previous = event_id
        path.write_text("\n".join(encoded) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(OrchestrationError, "lacks required fields"):
            prepare_launch(self.root, instruction_id, "codex")

    def test_single_incomplete_legacy_binding_requires_reconciliation(self) -> None:
        instruction_id = str(_test_identity()["launch_instruction_id"])
        material = {
            "schema_version": 1,
            "launch_instruction_id": instruction_id,
            "state": "PREPARED",
            "host": "codex",
            "attempt": 1,
            "retry_of": None,
            "previous_event_id": None,
            "recorded_at": "2026-08-14T00:00:00Z",
        }
        event_id = "sha256:" + sha256(
            json.dumps(
                material,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        execution_dir = _authority_state_dir(self.root)
        assert execution_dir is not None
        path = execution_dir / "task-bindings.jsonl"
        path.write_text(
            json.dumps({**material, "event_id": event_id}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            OrchestrationError,
            "lacks required fields",
        ):
            prepare_launch(self.root, instruction_id, "codex")

    def test_first_binding_read_waits_for_first_append_barrier(self) -> None:
        instruction_id = str(_test_identity()["launch_instruction_id"])
        append_entered = threading.Event()
        allow_append = threading.Event()
        original = orchestration_module._append_binding_event_unlocked

        def delayed_append(*args, **kwargs):
            append_entered.set()
            self.assertTrue(allow_append.wait(15))
            return original(*args, **kwargs)

        with patch.object(
            orchestration_module,
            "_append_binding_event_unlocked",
            side_effect=delayed_append,
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                writer = executor.submit(prepare_launch, self.root, instruction_id, "codex")
                # Fresh kernel/identity authentication intentionally precedes the
                # ledger append and may hash a full execution bundle on slower
                # Windows filesystems.  The synchronization assertion begins at
                # the append barrier, not at thread submission.
                self.assertTrue(append_entered.wait(15))
                reader = executor.submit(binding_events, self.root)
                self.assertFalse(reader.done())
                allow_append.set()
                written = writer.result(timeout=15)
                observed = reader.result(timeout=15)
        self.assertEqual([event["event_id"] for event in observed], [written["event_id"]])

    def test_empty_binding_read_is_non_mutating(self) -> None:
        root = self.root / "read-only-empty"
        (root / ".autopilot").mkdir(parents=True)
        state = root / ".autopilot" / "state"
        self.assertEqual(binding_events(root), ())
        self.assertFalse(state.exists())

    def test_production_binding_write_requires_explicit_runtime_migration(self) -> None:
        root = self.root / "uninitialized-production"
        (root / ".autopilot").mkdir(parents=True)
        for name in ("control-plane.json", "plan.json"):
            shutil.copy2(self.root / ".autopilot" / name, root / ".autopilot" / name)
        (root / ".git").mkdir()
        (root / ".git" / "config").write_text(
            '[remote "origin"]\n\turl = https://github.com/test/repo.git\n',
            encoding="utf-8",
            newline="\n",
        )
        instruction_id = str(_test_identity()["launch_instruction_id"])
        with self.assertRaisesRegex(
            OrchestrationError, "explicit authenticated execution directory"
        ):
            prepare_launch(root, instruction_id, "codex")
        ready_runtime(controller_module, root)
        prepared = prepare_launch(root, instruction_id, "codex")
        self.assertEqual(prepared["state"], "PREPARED")

    def test_implicit_completed_check_never_calls_mutating_status(self) -> None:
        completed = self.status([{"node_id": "ACTIVE-100", "state": "COMPLETE"}])
        completed["complete"] = True

        class StatusProbe:
            def __init__(self) -> None:
                self.status_calls = 0

            def observe_status(self):
                return completed

            def status(self):
                self.status_calls += 1
                return completed

        for request in ("", "What happened?"):
            probe = StatusProbe()
            _, decision = select_orchestration_status(probe, request)
            self.assertEqual(decision.intent, "CHECK")
            self.assertEqual(probe.status_calls, 0)

    def test_bound_host_task_prevents_false_quiescence(self) -> None:
        status = self.status([{"node_id": "ACTIVE-100", "state": "COMPLETE"}])
        status["complete"] = True
        plane = FakePlane(self.root, status, self.nodes)
        instruction_id = str(_test_identity()["launch_instruction_id"])
        prepare_launch(self.root, instruction_id, "codex")
        bind_launch(
            self.root, instruction_id, "codex", "thread-live",
            capability="capability"
        )
        contract = build_orchestration_contract(plane, "check", status=status)
        self.assertEqual(contract["outcome"], "ACTIVE")
        self.assertFalse(contract["quiescent"])

    def test_active_validation_lease_prevents_false_quiescence(self) -> None:
        status = self.status([{"node_id": "ACTIVE-100", "state": "COMPLETE"}])
        status["complete"] = True
        status["active_validation_lease"] = {
            "node_id": "ACTIVE-100",
            "owner": "curator:fixture",
            "expires_at": "2030-01-01T00:00:00Z",
        }
        plane = FakePlane(self.root, status, self.nodes)
        contract = build_orchestration_contract(plane, "check", status=status)
        self.assertEqual(contract["outcome"], "ACTIVE")
        self.assertFalse(contract["successful"])
        self.assertFalse(contract["quiescent"])

    def test_launch_identity_is_repository_scoped(self) -> None:
        rows = [{"node_id": "ACTIVE-100", "state": "READY", "reasons": []}]
        status = self.status(rows)
        status["dispatch_release"] = {"valid": True, "released_wave": ["ACTIVE-100"]}
        first = FakePlane(self.root, status, self.nodes)
        first.control = {"target": {"repository": "acme/one"}}
        second = FakePlane(self.root, status, self.nodes)
        second.control = {"target": {"repository": "acme/two"}}
        first_id = build_orchestration_contract(first, "start", status=status)["tasks"][0]["launch_instruction_id"]
        second_id = build_orchestration_contract(second, "start", status=status)["tasks"][0]["launch_instruction_id"]
        self.assertNotEqual(first_id, second_id)

    def test_check_is_read_only_even_when_work_is_ready(self) -> None:
        status = self.status([{"node_id": "NEW-300", "state": "READY"}])
        plane = FakePlane(self.root, status, self.nodes)
        contract = build_orchestration_contract(plane, "check status", status=status)
        self.assertEqual(contract["tasks"], [])
        self.assertFalse(contract["dispatch_required"])

    def test_adverse_settled_state_is_quiescent_but_not_success(self) -> None:
        status = self.status([{"node_id": "ACTIVE-100", "state": "QUARANTINED"}])
        status["complete"] = True
        plane = FakePlane(self.root, status, self.nodes)
        contract = build_orchestration_contract(plane, "finish", status=status)
        self.assertTrue(contract["quiescent"])
        self.assertEqual(contract["outcome"], "BLOCKED")
        self.assertFalse(contract["successful"])

    def test_nonterminal_blocker_is_not_quiescent(self) -> None:
        status = self.status([{"node_id": "ACTIVE-100", "state": "BLOCKED"}])
        plane = FakePlane(self.root, status, self.nodes)
        contract = build_orchestration_contract(plane, "finish", status=status)
        self.assertEqual(contract["outcome"], "BLOCKED")
        self.assertFalse(contract["quiescent"])

    def test_policy_and_simple_prompt_encode_required_behavior(self) -> None:
        policy = json.loads(
            (self.root / ".autopilot" / "orchestration-policy.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(validate_policy(policy), ())
        policy["task_transport"]["nested_primary_forbidden"] = False
        self.assertTrue(validate_policy(policy))
        prompt = simple_prompt()
        self.assertIn("Infer whether I mean", prompt)
        self.assertIn("quiescent", prompt)

    def test_policy_validation_rejects_disabled_execution_invariants(self) -> None:
        source = json.loads(
            (self.root / ".autopilot" / "orchestration-policy.json").read_text(
                encoding="utf-8"
            )
        )
        mutations = (
            ("polling", "poll_until_terminal", False),
            ("polling", "answer_questions_then_resume", False),
            ("recovery", "resume_same_task_after_fix", False),
            ("recovery", "blocker_is_completion", True),
            ("wave", "never_start_next_level_before_required_current_cohort_quiescence", False),
            ("task_transport", "record_task_id", False),
            (
                "parallel_task_cohort",
                "create_released_tasks_even_when_recovery_tasks_exist",
                False,
            ),
            ("parallel_task_cohort", "create_eligible_preparation_tasks", False),
            ("parallel_task_cohort", "create_entire_cohort_before_first_wait", False),
            ("parallel_task_cohort", "poll_every_created_task_to_terminal", False),
            (
                "parallel_task_cohort",
                "closure_target_prioritizes_collection_not_creation",
                False,
            ),
        )
        for section, key, value in mutations:
            with self.subTest(section=section, key=key):
                candidate = copy.deepcopy(source)
                candidate[section][key] = value
                self.assertTrue(validate_policy(candidate))


if __name__ == "__main__":
    unittest.main()
