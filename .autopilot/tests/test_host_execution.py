from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
import unittest
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence
from unittest import mock

BIN = Path(__file__).resolve().parents[1] / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

import controller as controller_module  # noqa: E402
import host_execution as host_execution_module  # noqa: E402
import test_app_server_host as app_server_fixture  # noqa: E402
from fixture_support import ready_runtime  # noqa: E402
from host_execution import (  # noqa: E402
    ACK_KIND,
    CONTRACT_KIND,
    CREATE_KIND,
    EVENT_KIND,
    SIDECAR_ACK_KIND,
    SIDECAR_CREATE_KIND,
    SIDECAR_EVENT_KIND,
    SIDECAR_RESULT_KIND,
    HostExecutionError,
)
from host_execution import (  # noqa: E402
    execute_contract as _execute_contract,
)
from orchestration import (  # noqa: E402
    bind_launch as _bind_launch,
)
from orchestration import (  # noqa: E402
    binding_events as _binding_events,
)
from orchestration import (  # noqa: E402
    derive_launch_identity,
)
from orchestration import (  # noqa: E402
    fence_launch as _fence_launch,
)
from orchestration import (  # noqa: E402
    launch_binding as _launch_binding,
)
from orchestration import (  # noqa: E402
    prepare_launch as _prepare_launch,
)
from orchestration import (  # noqa: E402
    release_terminal_launch as _release_terminal_launch,
)
from sidecar_execution import (  # noqa: E402
    active_sidecars as _active_sidecars,
)
from sidecar_execution import (  # noqa: E402
    make_descendant_spec,
    plan_sidecars,
    sidecar_spec_digest,
)
from sidecar_execution import (  # noqa: E402
    sidecar_events as _sidecar_events,
)

TARGET = "release/test"
TARGET_SHA = "a" * 40
REPOSITORY = "test/repo"
LIFECYCLE = "NODE_DELIVERY"
PLAN_MATERIAL = {
    "schema_version": 1,
    "plan_id": "host-execution-fixture",
    "title": "Host execution fixture",
    "subject": "authenticated host execution",
    "created_at": "2030-01-01T00:00:00Z",
    "baseline": {"target_sha": TARGET_SHA},
    "state_machine": {"terminal_states": ["COMPLETE"]},
    "nodes": [
        {"id": f"NODE-{index}", "branch": f"autopilot/node-{index}"}
        for index in range(9)
    ],
}
PLAN_FINGERPRINT = "sha256:" + sha256(
    json.dumps(
        PLAN_MATERIAL,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()
RELEASE_ID = "sha256:" + "f" * 64
EXECUTION_ID = "sha256:e4721b27bb9e4d6370eb058a64d4d893981cc104a7a6a838f45a564cf0a579ff"
EXECUTION_NAMESPACE = "default"
_HOST_RUNTIMES: dict[Path, Path] = {}
_EXECUTION_ADAPTER_IDENTITIES: dict[Path, Mapping[str, object]] = {}


def _synthetic_effect_provenance() -> dict[str, str]:
    record_id = "sha256:" + "6" * 64
    return {
        "host_kernel_generation": "sha256:" + "5" * 64,
        "execution_adapter_identity_record_id": record_id,
        "execution_adapter_identity_path": (
            "execution-adapter-bindings/"
            + record_id.removeprefix("sha256:")
            + ".json"
        ),
        "execution_adapter_identity_blob_digest": "sha256:" + "7" * 64,
    }


def _synthetic_effect_fence() -> host_execution_module._EffectFence:
    return host_execution_module._EffectFence(
        instruction_id="sha256:" + "1" * 64,
        resource_key="sha256:" + "2" * 64,
        authority_epoch=1,
        dispatch_release_id="sha256:" + "3" * 64,
        dispatch_admission_epoch=1,
        **_synthetic_effect_provenance(),
        task={"authority_class": "WRITE_AUTHORIZED", "node_id": "NODE-0"},
    )


def _execution_dir(root: Path) -> Path:
    coordination = controller_module.resolve_repository_state_dir(root)
    directory = controller_module.execution_namespace_dir(coordination, EXECUTION_ID)
    return controller_module.require_execution_authority_dir(
        root,
        directory,
        execution_id=EXECUTION_ID,
        execution_namespace=EXECUTION_NAMESPACE,
    )


def _identity(
    index: int,
    *,
    attempt: int = 1,
    retry_of: str | None = None,
) -> Mapping[str, object]:
    return derive_launch_identity(
        execution_id=EXECUTION_ID,
        execution_namespace=EXECUTION_NAMESPACE,
        repository=REPOSITORY,
        node_id=f"NODE-{index}",
        lifecycle=LIFECYCLE,
        authority_class="WRITE_AUTHORIZED",
        branch=f"autopilot/node-{index}",
        target_branch=TARGET,
        target_sha=TARGET_SHA,
        plan_fingerprint=PLAN_FINGERPRINT,
        attempt=attempt,
        retry_of=retry_of,
    )


def _resource(index: int) -> str:
    return str(_identity(index)["resource_key"])


def prepare_launch(root, instruction_id, host, **kwargs):
    repo_root = Path(root).resolve()
    execution_dir = _execution_dir(repo_root)
    kwargs.setdefault("state_dir", execution_dir)
    kwargs.setdefault("execution_id", EXECUTION_ID)
    kwargs.setdefault("execution_namespace", EXECUTION_NAMESPACE)
    kwargs.setdefault("repository", REPOSITORY)
    kwargs.setdefault("node_id", "NODE-0")
    kwargs.setdefault("lifecycle", LIFECYCLE)
    kwargs.setdefault("branch", "autopilot/node-0")
    kwargs.setdefault("resource_key", _resource(0))
    kwargs.setdefault("target_sha", TARGET_SHA)
    kwargs.setdefault("plan_fingerprint", PLAN_FINGERPRINT)
    kwargs.setdefault("target_branch", TARGET)
    kwargs.setdefault("authority_class", "WRITE_AUTHORIZED")
    kwargs.setdefault("dispatcher_release_id", RELEASE_ID)
    kwargs.setdefault("dispatcher_admission_epoch", 1)
    kwargs.setdefault(
        "host_reservation_id",
        controller_module.digest_json(
            {
                "kind": "hive-mind-host-test-reservation-v1",
                "launch_instruction_id": instruction_id,
            }
        ),
    )
    kwargs.setdefault("capacity_host_id", "host-1")
    kwargs.setdefault("capacity_generation", "sha256:" + "b" * 64)
    kwargs.setdefault("capacity_epoch", 1)
    kwargs.setdefault("reservation_expires_at", "2099-01-01T00:00:00Z")
    adapter_identity = _EXECUTION_ADAPTER_IDENTITIES[repo_root]
    host_runtime = _HOST_RUNTIMES[repo_root]
    host_identity = controller_module.read_strict_canonical_json(
        host_runtime / "host-runtime-identity.json",
        label="fixture host writer identity",
    )
    adapter_record_id = str(adapter_identity["record_id"])
    adapter_path = (
        host_runtime
        / "execution-adapter-bindings"
        / (adapter_record_id.removeprefix("sha256:") + ".json")
    )
    kwargs.setdefault(
        "host_kernel_generation", host_identity["host_kernel_generation"]
    )
    kwargs.setdefault("execution_adapter_identity_record_id", adapter_record_id)
    kwargs.setdefault(
        "execution_adapter_identity_path",
        str(adapter_path.relative_to(host_runtime)).replace("\\", "/"),
    )
    kwargs.setdefault(
        "execution_adapter_identity_blob_digest",
        "sha256:" + sha256(adapter_path.read_bytes()).hexdigest(),
    )
    with controller_module.runtime_file_lock(
        execution_dir / "locks" / "dispatcher-admission.lock",
        timeout_seconds=120.0,
    ):
        return _prepare_launch(root, instruction_id, host, **kwargs)


def launch_binding(root, instruction_id, **kwargs):
    kwargs.setdefault("state_dir", _execution_dir(Path(root)))
    return _launch_binding(root, instruction_id, **kwargs)


def binding_events(root, **kwargs):
    kwargs.setdefault("state_dir", _execution_dir(Path(root)))
    return _binding_events(root, **kwargs)


def fence_launch(root, instruction_id, **kwargs):
    execution_dir = _execution_dir(Path(root))
    kwargs.setdefault("state_dir", execution_dir)
    with controller_module.runtime_file_lock(
        execution_dir / "locks" / "dispatcher-admission.lock",
        timeout_seconds=120.0,
    ):
        return _fence_launch(root, instruction_id, **kwargs)


def active_sidecars(root, **kwargs):
    kwargs.setdefault("state_dir", _execution_dir(Path(root)))
    return _active_sidecars(root, **kwargs)


def sidecar_events(root, **kwargs):
    kwargs.setdefault("state_dir", _execution_dir(Path(root)))
    return _sidecar_events(root, **kwargs)


def _fence(root: Path, instruction_id: str) -> tuple[str, int]:
    value = launch_binding(root, instruction_id)
    if value is None:
        raise AssertionError("test launch has no binding")
    return str(value["resource_key"]), int(value["authority_epoch"])


def bind_launch(root, instruction_id, host, task_id, **kwargs):
    execution_dir = _execution_dir(Path(root))
    resource_key, authority_epoch = _fence(root, instruction_id)
    kwargs.setdefault("resource_key", resource_key)
    kwargs.setdefault("authority_epoch", authority_epoch)
    kwargs.setdefault("state_dir", execution_dir)
    with controller_module.runtime_file_lock(
        execution_dir / "locks" / "dispatcher-admission.lock",
        timeout_seconds=120.0,
    ):
        return _bind_launch(root, instruction_id, host, task_id, **kwargs)


def release_terminal_launch(root, instruction_id, **kwargs):
    execution_dir = _execution_dir(Path(root))
    resource_key, authority_epoch = _fence(root, instruction_id)
    kwargs.setdefault("resource_key", resource_key)
    kwargs.setdefault("authority_epoch", authority_epoch)
    kwargs.setdefault("state_dir", execution_dir)
    with controller_module.runtime_file_lock(
        execution_dir / "locks" / "dispatcher-admission.lock",
        timeout_seconds=120.0,
    ):
        return _release_terminal_launch(root, instruction_id, **kwargs)


def _rehash(value: dict[str, Any]) -> dict[str, Any]:
    material = dict(value)
    material.pop("contract_id", None)
    value["contract_id"] = "sha256:" + sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return value


def execute_contract(root, contract, adapter, resolver, **kwargs):
    repo_root = Path(root).resolve()
    execution_dir = _execution_dir(repo_root)
    host_runtime = _HOST_RUNTIMES[repo_root]
    adapter.host_runtime_dir = host_runtime
    adapter.repo_root = repo_root
    adapter.execution_dir = execution_dir
    adapter.execution_id = EXECUTION_ID
    adapter.execution_namespace = EXECUTION_NAMESPACE
    adapter_identity_source = adapter.host_provider_identity(repo_root=repo_root)
    candidate = json.loads(json.dumps(contract))
    release = candidate.setdefault("dispatch_release", {})
    release.setdefault("admission_epoch", 1)
    permits: list[Mapping[str, object]] = []
    capacity = controller_module.read_host_capacity(
        host_runtime, "host-1", now=controller_module.utc_now()
    )
    with controller_module.runtime_file_lock(
        host_runtime / "locks" / "host-authority.lock",
        timeout_seconds=120.0,
    ):
        execution_adapter_identity = controller_module.install_execution_adapter_identity(
            host_runtime,
            repo_root=repo_root,
            execution_dir=execution_dir,
            execution_namespace=EXECUTION_NAMESPACE,
            execution_id=EXECUTION_ID,
            host_id="host-1",
            adapter_identity_path=(
                execution_dir / "host" / "codex-app-server-v1" / "identity.json"
            ),
            adapter_identity=adapter_identity_source,
        )
        for task in candidate.get("tasks", []):
            if task.get("authority_class") != "WRITE_AUTHORIZED":
                continue
            persisted = _launch_binding(
                repo_root,
                str(task["launch_instruction_id"]),
                state_dir=execution_dir,
            )
            if isinstance(persisted, Mapping) and persisted.get("state") == "RELEASED":
                continue
            demand = controller_module.record_host_scheduler_demand(
                host_runtime,
                host_id="host-1",
                repository=str(task["repository"]),
                repository_transport_digest=str(
                    controller_module.runtime_repository_identity(repo_root)[
                        "transport_digest"
                    ]
                ),
                execution_namespace=EXECUTION_NAMESPACE,
                execution_id=EXECUTION_ID,
                plan_fingerprint=str(task["plan_fingerprint"]),
                capacity_generation=str(capacity["capacity_generation"]),
                execution_adapter_identity=execution_adapter_identity,
                candidate_reservation_ids=[str(task["launch_instruction_id"])],
                weight=1,
                actor="test:host-scheduler",
                recorded_at=str(capacity["issued_at"]),
            )
            schedule = controller_module.grant_host_scheduler_capacity(
                host_runtime,
                host_id="host-1",
                actor="test:host-scheduler",
                now=controller_module.utc_now(),
            )
            grant = next(
                item
                for item in schedule["outstanding_grants"]
                if item.get("demand_id") == demand.get("demand_id")
            )
            permit = controller_module.reserve_global_host_session(
                host_runtime,
                repository=str(task["repository"]),
                execution_id=EXECUTION_ID,
                host_id="host-1",
                capacity_generation=str(capacity["capacity_generation"]),
                local_reservation_id=str(task["launch_instruction_id"]),
                reservation_kind="PRIMARY",
                resource_key=str(task["resource_key"]),
                write_scopes=(),
                actor_time=str(capacity["issued_at"]),
                expires_at=str(capacity["expires_at"]),
                now=controller_module.utc_now(),
                execution_adapter_identity=execution_adapter_identity,
                host_scheduler_grant_id=str(grant["grant_id"]),
            )
            permits.append(
                {
                    "node_id": task["node_id"],
                    "resource_key": task["resource_key"],
                    "reservation_id": permit["reservation_id"],
                }
            )
    release["primary_host_reservations"] = permits
    _rehash(candidate)
    kwargs.setdefault("state_dir", execution_dir)
    kwargs.setdefault("host_runtime_dir", host_runtime)
    return _execute_contract(repo_root, candidate, adapter, resolver, **kwargs)


def _contract(*, tasks: int = 2) -> dict[str, Any]:
    rows = []
    for index in range(tasks):
        identity = _identity(index)
        instruction_id = str(identity["launch_instruction_id"])
        rows.append(
            {
                "task_key": f"NODE-{index}",
                "execution_id": EXECUTION_ID,
                "execution_namespace": EXECUTION_NAMESPACE,
                "capacity_host_id": "host-1",
                "resource_key": identity["resource_key"],
                "repository": REPOSITORY,
                "node_id": f"NODE-{index}",
                "lifecycle": LIFECYCLE,
                "branch": f"autopilot/node-{index}",
                "launch_instruction_id": instruction_id,
                "idempotency_key": instruction_id,
                "attempt": 1,
                "retry_of": None,
                "title": f"Node {index}",
                "prompt": f"Execute node {index}",
                "required": True,
                "target_branch": TARGET,
                "target_sha": TARGET_SHA,
                "plan_fingerprint": PLAN_FINGERPRINT,
                "authority_mode": "EXECUTION_AUTHORIZED",
                "authority_class": "WRITE_AUTHORIZED",
                "transport": "durable_user_owned_task",
            }
        )
    return _rehash(
        {
            "schema_version": 1,
            "kind": CONTRACT_KIND,
            "execution_id": EXECUTION_ID,
            "execution_namespace": EXECUTION_NAMESPACE,
            "capacity_host_id": "host-1",
            "target_branch": TARGET,
            "target_sha": TARGET_SHA,
            "plan_fingerprint": PLAN_FINGERPRINT,
            "dispatch_release": {
                "valid": True,
                "release_id": RELEASE_ID,
                "released_wave": [f"NODE-{index}" for index in range(tasks)],
            },
            "tasks": rows,
            "active_claims": [],
            "active_validation_lease": None,
            "execution": {
                "create_all_parallel_safe_primary_tasks": True,
                "poll_until_terminal": True,
                "answer_and_resume_blocked_tasks": True,
                "parent_final_while_required_tasks_active": False,
            },
        }
    )


def _sidecar_contract(*, primary_tasks: int = 1) -> dict[str, Any]:
    contract = _contract(tasks=primary_tasks)
    policy = json.loads((Path(__file__).resolve().parents[1] / "orchestration-policy.json").read_text(encoding="utf-8"))["sidecars"]
    node = {"risk": "high", "read_scope": ["a", "b", "c"], "evidence_requirements": ["x"]}
    sidecars = list(plan_sidecars(contract["tasks"][:1], {"NODE-0": node}, policy))
    contract["tasks"][0]["sidecars"] = sidecars
    contract["sidecar_cohort"] = {
        "size": len(sidecars),
        "sidecar_ids": [item["sidecar_id"] for item in sidecars],
        "canonical_host_cap": 8,
        "initial_host_reservations": primary_tasks + len(sidecars),
        "remaining_descendant_slots": 8 - primary_tasks - len(sidecars),
        "planned_token_budget": sum(item["token_budget"] for item in sidecars),
        "estimated_net_savings_tokens": sum(item["estimated_net_savings_tokens"] for item in sidecars),
        "root_mediated": True,
        "all_parents_require_terminal_ack": True,
        "policy": policy,
    }
    return _rehash(contract)


class Resolver:
    def __init__(self) -> None:
        self.questions: list[str] = []

    def resolve_attention(
        self, task: Mapping[str, object], event: Mapping[str, object]
    ) -> str:
        self.questions.append(str(event["attention"]))
        return f"resolved for {task['node_id']}"


class Adapter:
    def __init__(self, script: Sequence[Sequence[Mapping[str, object]]]) -> None:
        self.host_id = "host-1"
        self.script = list(script)
        self.created: list[str] = []
        self.prompts: dict[str, str] = {}
        self.lookup_count = 0
        self.wait_create_counts: list[int] = []
        self.wait_target_counts: list[int] = []
        self.messages: dict[str, str] = {}
        self.bindings: dict[str, dict[str, str]] = {}
        self.trusted_target = TARGET
        self.runtime: dict[str, object] = {
            "target_branch": TARGET,
            "active_claims": [],
            "active_validation_lease": None,
            "quiescent": True,
        }
        self.fail_after_first_message = False
        self.reject_dispatch_release = False
        self.dispatch_guard_depth = 0
        self.dispatch_guards: list[tuple[str, str]] = []
        self.external_effects: list[tuple[str, int]] = []
        self.host_runtime_dir: Path | None = None

    def host_provider_identity(self, *, repo_root: Path) -> Mapping[str, object]:
        if self.host_runtime_dir is None:
            raise AssertionError("test host runtime was not installed")
        execution_dir = _execution_dir(Path(repo_root).resolve())
        provider = controller_module._host_provider_binding(
            self.host_runtime_dir, host_id=self.host_id
        )
        runtime_identity = controller_module.read_strict_canonical_json(
            self.host_runtime_dir / "host-runtime-identity.json",
            label="fixture host runtime identity",
        )
        source_path = Path(controller_module.__file__).resolve()
        source_digest = "sha256:" + sha256(source_path.read_bytes()).hexdigest()
        digest = "sha256:" + "e" * 64
        material: dict[str, object] = {
            "schema_version": 1,
            "kind": "hive-mind-codex-app-server-identity-v1",
            "execution_namespace": EXECUTION_NAMESPACE,
            "execution_id": EXECUTION_ID,
            "host_id": self.host_id,
            "machine_user_id": runtime_identity["machine_user_id"],
            "provider_identity_digest": provider["provider_identity_digest"],
            "adapter_module_path": str(source_path),
            "adapter_module_digest": source_digest,
            "launcher_path": str(source_path),
            "launcher_digest": source_digest,
            "cli_module_path": None,
            "cli_module_digest": None,
            "executable_path": str(source_path),
            "executable_digest": source_digest,
            "executable_version": "test-fixture",
            "schema_bundle_digest": digest,
            "thread_start_schema_digest": digest,
            "turn_start_schema_digest": digest,
            "environment_root_digest": digest,
            "behavior_environment_digest": digest,
            "provider_config_digest": digest,
            "execution_config_digest": digest,
            "account_identity_digest": digest,
            "effective_model": "test-model",
            "effective_model_provider": "test-provider",
            "transport": "stdio://",
            "initialize_result_digest": digest,
            "created_at": "2030-01-01T00:00:00Z",
        }
        identity = {
            **material,
            "record_id": controller_module.digest_json(material),
        }
        controller_module.atomic_write_json(
            execution_dir / "host" / "codex-app-server-v1" / "identity.json",
            identity,
        )
        self.provider_identity_digest = provider["provider_identity_digest"]
        self.repo_root = Path(repo_root).resolve()
        self.execution_dir = execution_dir
        self.execution_id = EXECUTION_ID
        self.execution_namespace = EXECUTION_NAMESPACE
        return identity

    def host_lifecycle_authority(self, *, repo_root: Path) -> Mapping[str, object]:
        del repo_root
        material: dict[str, object] = {
            "schema_version": 1,
            "kind": "hive-mind-host-lifecycle-capability-v1",
            "host_id": "host-1",
            "create": True,
            "query": True,
            "resume": True,
            "interrupt": True,
            "archive": True,
            "autonomous_launch": True,
            "source": "fixture:authenticated-host",
        }
        return {**material, "record_id": controller_module.digest_json(material)}

    def host_capacity_authority(self, *, repo_root: Path) -> Mapping[str, object]:
        del repo_root
        if self.host_runtime_dir is None:
            raise AssertionError("test host runtime was not installed")
        return controller_module.read_host_capacity(
            self.host_runtime_dir,
            "host-1",
            now=controller_module.utc_now(),
        )

    def trusted_singleton_target(self, *, repo_root: Path) -> str:
        del repo_root
        return self.trusted_target

    @contextmanager
    def dispatcher_effect_guard(self, *, node_id: str, release_id: str):
        self.dispatch_guards.append((node_id, release_id))
        if self.reject_dispatch_release:
            raise RuntimeError("stale dispatcher release")
        self.dispatch_guard_depth += 1
        try:
            yield
        finally:
            self.dispatch_guard_depth -= 1

    def seed(self, instruction_id: str, index: int = 0) -> dict[str, object]:
        binding = {
            "host_id": "host-1",
            "task_id": f"task-{index}",
            "cursor": f"binding-cursor-{index}",
            "capability": f"capability-{index}",
        }
        self.bindings[instruction_id] = binding
        return {"kind": CREATE_KIND, **binding, "idempotency_key": instruction_id}

    def lookup_thread(self, *, idempotency_key: str) -> Mapping[str, object] | None:
        self.lookup_count += 1
        binding = self.bindings.get(idempotency_key)
        return None if binding is None else {
            "kind": CREATE_KIND,
            **binding,
            "idempotency_key": idempotency_key,
        }

    def create_thread(
        self, *, title: str, prompt: str, idempotency_key: str
    ) -> Mapping[str, object]:
        del title
        self.external_effects.append(("create_thread", self.dispatch_guard_depth))
        existing = self.lookup_thread(idempotency_key=idempotency_key)
        if existing is not None:
            return existing
        index = len(self.bindings)
        self.created.append(idempotency_key)
        self.prompts[idempotency_key] = prompt
        return self.seed(idempotency_key, index)

    def wait_threads(
        self, targets: Sequence[Mapping[str, object]]
    ) -> Sequence[Mapping[str, object]]:
        self.wait_create_counts.append(len(self.created))
        self.wait_target_counts.append(len(targets))
        if not self.script:
            return []
        batch = []
        for event in self.script.pop(0):
            material = dict(event)
            instruction_id = str(material.pop("instruction_id"))
            material.update(self.bindings[instruction_id])
            batch.append(material)
        return batch

    def send_message_to_thread(
        self,
        *,
        host_id: str,
        task_id: str,
        cursor: str,
        capability: str,
        message: str,
        idempotency_key: str,
    ) -> Mapping[str, object]:
        self.external_effects.append(("send_message_to_thread", self.dispatch_guard_depth))
        self.messages.setdefault(idempotency_key, message)
        if self.fail_after_first_message:
            self.fail_after_first_message = False
            raise RuntimeError("simulated parent crash after accepted message")
        return {
            "kind": ACK_KIND,
            "host_id": host_id,
            "task_id": task_id,
            "cursor": cursor,
            "capability": capability,
            "accepted": True,
            "message_id": f"message-{idempotency_key[-8:]}",
            "idempotency_key": idempotency_key,
        }

    def inspect_runtime_authority(self, *, repo_root: Path) -> Mapping[str, object]:
        del repo_root
        return self.runtime


class SidecarAdapter(Adapter):
    def __init__(self, script: Sequence[Mapping[str, object]]) -> None:
        super().__init__([])
        self.activity_script = list(script)
        self.sidecar_bindings: dict[str, dict[str, str]] = {}
        self.sidecar_spawned: list[str] = []
        self.sidecar_messages: list[str] = []
        self.sidecar_closed: list[str] = []

    def lookup_sidecar(self, *, idempotency_key: str) -> Mapping[str, object] | None:
        binding = self.sidecar_bindings.get(idempotency_key)
        if binding is None:
            return None
        parent = next(task for task in self.contract["tasks"] if any(item["sidecar_id"] == idempotency_key for item in task.get("sidecars", [])))
        return {"kind": SIDECAR_CREATE_KIND, **binding, "idempotency_key": idempotency_key, "parent_launch_instruction_id": parent["launch_instruction_id"]}

    def spawn_sidecar(self, *, prompt: str, token_budget: int, idempotency_key: str, parent_launch_instruction_id: str) -> Mapping[str, object]:
        del prompt, token_budget
        self.external_effects.append(("spawn_sidecar", self.dispatch_guard_depth))
        existing = self.sidecar_bindings.get(idempotency_key)
        if existing is None:
            index = len(self.sidecar_bindings)
            existing = {"host_id": "host-1", "sidecar_task_id": f"sidecar-{index}", "cursor": f"sidecar-cursor-{index}", "capability": f"sidecar-capability-{index}"}
            self.sidecar_bindings[idempotency_key] = existing
            self.sidecar_spawned.append(idempotency_key)
        return {"kind": SIDECAR_CREATE_KIND, **existing, "idempotency_key": idempotency_key, "parent_launch_instruction_id": parent_launch_instruction_id}

    def wait_activity(self, primary_targets: Sequence[Mapping[str, object]], sidecar_targets: Sequence[Mapping[str, object]]) -> Mapping[str, object]:
        del primary_targets, sidecar_targets
        if not self.activity_script:
            return {"primary_events": [], "sidecar_events": []}
        batch = dict(self.activity_script.pop(0))
        primary = []
        for event in batch.get("primary_events", []):
            material = dict(event)
            instruction_id = str(material.pop("instruction_id"))
            material.update(self.bindings[instruction_id])
            primary.append(material)
        sidecars = []
        for event in batch.get("sidecar_events", []):
            material = dict(event)
            sidecar_id = str(material["sidecar_id"])
            material.update(self.sidecar_bindings[sidecar_id])
            sidecars.append(material)
        return {"primary_events": primary, "sidecar_events": sidecars}

    def send_message_to_sidecar(self, *, host_id: str, sidecar_task_id: str, cursor: str, capability: str, message: str, idempotency_key: str) -> Mapping[str, object]:
        self.external_effects.append(("send_message_to_sidecar", self.dispatch_guard_depth))
        self.sidecar_messages.append(message)
        return {"kind": SIDECAR_ACK_KIND, "host_id": host_id, "sidecar_task_id": sidecar_task_id, "cursor": cursor, "capability": capability, "accepted": True, "message_id": f"sidecar-message-{len(self.sidecar_messages)}", "idempotency_key": idempotency_key}

    def close_sidecar(self, *, host_id: str, sidecar_task_id: str, cursor: str, capability: str, reason: str, idempotency_key: str) -> Mapping[str, object]:
        del reason, idempotency_key
        self.external_effects.append(("close_sidecar", self.dispatch_guard_depth))
        sidecar_id = next(key for key, value in self.sidecar_bindings.items() if value["sidecar_task_id"] == sidecar_task_id)
        self.sidecar_closed.append(sidecar_id)
        spec = next(item for task in self.contract["tasks"] for item in task.get("sidecars", []) if item["sidecar_id"] == sidecar_id)
        return {"kind": SIDECAR_EVENT_KIND, "host_id": host_id, "sidecar_task_id": sidecar_task_id, "cursor": cursor, "capability": capability, "sidecar_id": sidecar_id, "state": "CANCELLED", "event_id": f"close-{sidecar_id[-8:]}", "event_cursor": "closed", "result": _sidecar_result(spec, "CANCELLED")}


def _event(instruction_id: str, state: str, cursor: str, **extra: object) -> dict[str, object]:
    return {
        "kind": EVENT_KIND,
        "instruction_id": instruction_id,
        "state": state,
        "event_id": f"event-{instruction_id[-8:]}-{cursor}",
        "event_cursor": cursor,
        **extra,
    }


def _sidecar_result(spec: Mapping[str, object], status: str = "SUCCEEDED", usage: int = 100) -> dict[str, object]:
    return {"kind": SIDECAR_RESULT_KIND, "sidecar_id": spec["sidecar_id"], "parent_launch_instruction_id": spec["parent_launch_instruction_id"], "spec_digest": sidecar_spec_digest(spec), "status": status, "summary": "bounded result", "findings": [], "evidence_refs": ["tests"], "blocker": None, "token_usage": usage}


def _sidecar_event(spec: Mapping[str, object], state: str, cursor: str, **extra: object) -> dict[str, object]:
    return {"kind": SIDECAR_EVENT_KIND, "sidecar_id": spec["sidecar_id"], "state": state, "event_id": f"sidecar-event-{spec['sidecar_id'][-8:]}-{cursor}", "event_cursor": cursor, **extra}


def _write_authority_fixture(root: Path) -> None:
    source = Path(__file__).resolve().parents[1]
    control = json.loads((source / "control-plane.json").read_text(encoding="utf-8"))
    control["target"]["repository"] = REPOSITORY
    control["target"]["branch"] = TARGET
    control["target"]["baseline_sha"] = TARGET_SHA
    control["plan_fingerprint"] = PLAN_FINGERPRINT
    control["verify_git_objects"] = False
    controller_module.atomic_write_json(
        root / ".autopilot" / "control-plane.json", control
    )
    controller_module.atomic_write_json(
        root / ".autopilot" / "plan.json",
        {**PLAN_MATERIAL, "plan_fingerprint": PLAN_FINGERPRINT},
    )


class HostExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / ".autopilot").mkdir()
        source = Path(__file__).resolve().parents[1]
        shutil.copy2(source / "task-bindings.lock", self.root / ".autopilot" / "task-bindings.lock")
        shutil.copy2(source / "sidecar-bindings.lock", self.root / ".autopilot" / "sidecar-bindings.lock")
        _write_authority_fixture(self.root)
        ready_runtime(controller_module, self.root)
        self.host_base_patch = mock.patch.object(
            controller_module,
            "_host_runtime_base_dir",
            return_value=self.root / "host-account-authority",
        )
        self.host_base_patch.start()
        self.host_runtime = self.root / "host-runtime"
        controller_module.initialize_host_runtime(self.host_runtime)
        now = controller_module.utc_now()
        provider_attestation = controller_module.build_host_provider_attestation(
            self.host_runtime,
            host_id="host-1",
            provider_identity_source="fixture:host-adapter",
            provider_identity_material={
                "kind": "hive-mind-test-host-provider-v1",
                "identity_token": "sha256:" + "d" * 64,
            },
        )
        with controller_module.runtime_file_lock(
            self.host_runtime / "locks" / "host-authority.lock",
            timeout_seconds=120.0,
        ):
            controller_module.publish_host_capacity(
                self.host_runtime,
                host_id="host-1",
                capacity_generation="sha256:" + "b" * 64,
                capacity_epoch=1,
                max_total_sessions=16,
                validation_slots=1,
                issued_at=controller_module.format_time(now),
                expires_at=controller_module.format_time(now + timedelta(days=1)),
                capability_source="fixture:authenticated-capacity",
                capability_digest="sha256:" + "c" * 64,
                provider_identity_source="fixture:host-adapter",
                provider_identity_digest=provider_attestation[
                    "provider_identity_digest"
                ],
                provider_attestation=provider_attestation,
                declarative=False,
                now=now,
                expected_generation=None,
            )
        repo_root = self.root.resolve()
        _HOST_RUNTIMES[repo_root] = self.host_runtime
        fixture_adapter = Adapter([])
        fixture_adapter.host_runtime_dir = self.host_runtime
        identity_source = fixture_adapter.host_provider_identity(repo_root=repo_root)
        with controller_module.runtime_file_lock(
            self.host_runtime / "locks" / "host-authority.lock",
            timeout_seconds=120.0,
        ):
            _EXECUTION_ADAPTER_IDENTITIES[repo_root] = (
                controller_module.install_execution_adapter_identity(
                    self.host_runtime,
                    repo_root=repo_root,
                    execution_dir=_execution_dir(repo_root),
                    execution_namespace=EXECUTION_NAMESPACE,
                    execution_id=EXECUTION_ID,
                    host_id="host-1",
                    adapter_identity_path=(
                        _execution_dir(repo_root)
                        / "host"
                        / "codex-app-server-v1"
                        / "identity.json"
                    ),
                    adapter_identity=identity_source,
                )
            )

    def tearDown(self) -> None:
        _EXECUTION_ADAPTER_IDENTITIES.pop(self.root.resolve(), None)
        _HOST_RUNTIMES.pop(self.root.resolve(), None)
        self.host_base_patch.stop()
        self.temporary.cleanup()

    def test_creates_entire_parallel_wave_before_first_wait(self) -> None:
        contract = _contract()
        ids = [str(task["launch_instruction_id"]) for task in contract["tasks"]]
        adapter = Adapter([[_event(ids[0], "SUCCEEDED", "1"), _event(ids[1], "SUCCEEDED", "1")]])
        result = execute_contract(self.root, contract, adapter, Resolver())
        self.assertEqual(adapter.wait_create_counts, [2])
        for instruction_id in ids:
            prepared = next(
                event
                for event in binding_events(self.root)
                if event["launch_instruction_id"] == instruction_id
                and event["state"] == "PREPARED"
            )
            self.assertIn(
                f"--authority-epoch {prepared['authority_epoch']}",
                adapter.prompts[instruction_id],
            )
            prompt = adapter.prompts[instruction_id]
            self.assertIn("--state-dir \"", prompt)
            for command in (
                " claim ",
                " heartbeat ",
                " fail ",
                " release ",
                " complete ",
                " validation-lease-acquire ",
                " validation-lease-renew ",
                " validation-lease-release ",
            ):
                with self.subTest(instruction_id=instruction_id, command=command):
                    self.assertIn(command, prompt)
            self.assertIn(
                f"--launch-instruction-id {instruction_id} "
                f"--resource-key {prepared['resource_key']} "
                f"--authority-epoch {prepared['authority_epoch']}",
                prompt,
            )
        self.assertTrue(result["successful"])
        self.assertTrue(result["quiescent"])
        self.assertEqual(
            {node for node, release in adapter.dispatch_guards if release == RELEASE_ID},
            {"NODE-0", "NODE-1"},
        )
        # Authority locks protect durable effect intent/reconciliation, never
        # the external host request itself.
        self.assertTrue(all(depth == 0 for _, depth in adapter.external_effects))

    def test_attention_self_heals_sends_answer_and_resumes(self) -> None:
        contract = _contract(tasks=1)
        instruction_id = str(contract["tasks"][0]["launch_instruction_id"])
        adapter = Adapter(
            [[_event(instruction_id, "NEEDS_ATTENTION", "1", attention="need a safe fix")],
             [_event(instruction_id, "SUCCEEDED", "2")]]
        )
        result = execute_contract(self.root, contract, adapter, Resolver())
        self.assertEqual(list(adapter.messages.values()), ["resolved for NODE-0"])
        self.assertEqual(adapter.wait_create_counts, [1, 1])
        self.assertTrue(result["successful"])

    def test_attention_message_is_idempotent_across_parent_crash(self) -> None:
        contract = _contract(tasks=1)
        instruction_id = str(contract["tasks"][0]["launch_instruction_id"])
        attention = _event(instruction_id, "NEEDS_ATTENTION", "1", attention="recover")
        adapter = Adapter([[attention]])
        adapter.fail_after_first_message = True
        with self.assertRaisesRegex(RuntimeError, "simulated parent crash"):
            execute_contract(self.root, contract, adapter, Resolver())
        adapter.script = [[attention], [_event(instruction_id, "SUCCEEDED", "2")]]
        result = execute_contract(self.root, contract, adapter, Resolver())
        self.assertTrue(result["successful"])
        self.assertEqual(len(adapter.messages), 1)
        self.assertEqual(adapter.created, [instruction_id])

    def test_fence_during_wait_rejects_later_message_and_terminal_write(self) -> None:
        for state, extra in (
            ("NEEDS_ATTENTION", {"attention": "stale question"}),
            ("SUCCEEDED", {}),
        ):
            with self.subTest(state=state):
                root = self.root / state.lower()
                (root / ".autopilot").mkdir(parents=True)
                _write_authority_fixture(root)
                ready_runtime(controller_module, root)
                contract = _contract(tasks=1)
                instruction_id = str(contract["tasks"][0]["launch_instruction_id"])
                adapter = Adapter([[_event(instruction_id, state, "1", **extra)]])
                original_wait = adapter.wait_threads

                def fenced_wait(targets):
                    result = original_wait(targets)
                    fence_launch(
                        root,
                        instruction_id,
                        actor="curator:test",
                        reason="fence landed while host wait was blocked",
                    )
                    return result

                adapter.wait_threads = fenced_wait  # type: ignore[method-assign]
                with self.assertRaisesRegex(HostExecutionError, "revoked"):
                    execute_contract(root, contract, adapter, Resolver())
                self.assertEqual(adapter.messages, {})
                self.assertEqual(binding_events(root)[-1]["state"], "SUPERSEDED")
                self.assertFalse(
                    any(event.get("state") == "RELEASED" for event in binding_events(root))
                )

    def test_prepared_launch_adopts_lookup_without_duplicate_create(self) -> None:
        contract = _contract(tasks=1)
        instruction_id = str(contract["tasks"][0]["launch_instruction_id"])
        prepare_launch(self.root, instruction_id, "codex")
        adapter = Adapter([[_event(instruction_id, "SUCCEEDED", "1")]])
        adapter.seed(instruction_id)
        result = execute_contract(self.root, contract, adapter, Resolver())
        self.assertTrue(result["successful"])
        self.assertEqual(adapter.created, [])

    def test_bound_launch_requires_lookup_and_adopts_exact_capability(self) -> None:
        contract = _contract(tasks=1)
        instruction_id = str(contract["tasks"][0]["launch_instruction_id"])
        adapter = Adapter([[_event(instruction_id, "SUCCEEDED", "1")]])
        adapter.seed(instruction_id)
        prepare_launch(self.root, instruction_id, "codex")
        bind_launch(
            self.root, instruction_id, "codex", "task-0",
            host_id="host-1", cursor="binding-cursor-0", capability="capability-0"
        )
        result = execute_contract(self.root, contract, adapter, Resolver())
        self.assertTrue(result["successful"])
        self.assertEqual(adapter.created, [])

    def test_forged_capability_event_is_rejected_without_terminal_release(self) -> None:
        contract = _contract(tasks=1)
        instruction_id = str(contract["tasks"][0]["launch_instruction_id"])
        adapter = Adapter([[_event(instruction_id, "SUCCEEDED", "1")]])
        original_wait = adapter.wait_threads

        def forged_wait(targets: Sequence[Mapping[str, object]]) -> Sequence[Mapping[str, object]]:
            events = [dict(item) for item in original_wait(targets)]
            events[0]["capability"] = "forged-capability"
            return events

        adapter.wait_threads = forged_wait  # type: ignore[method-assign]
        with self.assertRaisesRegex(HostExecutionError, "forged or mismatched capability"):
            execute_contract(self.root, contract, adapter, Resolver())
        self.assertEqual(binding_events(self.root)[-1]["state"], "BOUND")

    def test_required_active_task_prevents_success_and_quiescence(self) -> None:
        contract = _contract(tasks=1)
        adapter = Adapter([[], []])
        result = execute_contract(
            self.root, contract, adapter, Resolver(), max_no_progress_cycles=2
        )
        self.assertEqual(result["blocker"]["code"], "HOST_NO_PROGRESS_LIMIT")
        self.assertFalse(result["quiescent"])

    def test_total_poll_bound_stops_endless_unique_progress(self) -> None:
        contract = _contract(tasks=1)
        instruction_id = str(contract["tasks"][0]["launch_instruction_id"])
        adapter = Adapter([[_event(instruction_id, "ACTIVE", str(index))] for index in range(1, 5)])
        result = execute_contract(
            self.root, contract, adapter, Resolver(), max_poll_cycles=3
        )
        self.assertEqual(result["blocker"]["code"], "HOST_TOTAL_POLL_LIMIT")
        self.assertFalse(result["quiescent"])

    def test_oversized_primary_cohort_is_rejected_before_host_effects(self) -> None:
        contract = _contract(tasks=9)
        adapter = Adapter([])

        with self.assertRaisesRegex(
            HostExecutionError, "primary task cohort exceeds canonical cap 8"
        ):
            execute_contract(self.root, contract, adapter, Resolver())

        self.assertEqual(adapter.created, [])
        self.assertEqual(binding_events(self.root), ())

    def test_combined_primary_and_sidecar_overflow_is_rejected_before_host_effects(self) -> None:
        contract = _sidecar_contract(primary_tasks=7)
        self.assertGreater(
            len(contract["tasks"]) + int(contract["sidecar_cohort"]["size"]),
            8,
        )
        adapter = SidecarAdapter([])
        adapter.contract = contract

        with self.assertRaisesRegex(
            HostExecutionError, "attended host cohort exceeds canonical cap 8"
        ):
            execute_contract(self.root, contract, adapter, Resolver())

        self.assertEqual(adapter.external_effects, [])
        self.assertEqual(adapter.lookup_count, 0)
        self.assertEqual(binding_events(self.root), ())

    def test_stale_dispatcher_guard_fences_prepared_launch_without_host_effect(self) -> None:
        contract = _contract(tasks=1)
        instruction_id = str(contract["tasks"][0]["launch_instruction_id"])
        adapter = Adapter([])
        adapter.reject_dispatch_release = True

        with self.assertRaisesRegex(HostExecutionError, "stale dispatcher release"):
            execute_contract(self.root, contract, adapter, Resolver())

        self.assertEqual(adapter.external_effects, [])
        self.assertEqual(adapter.created, [])
        self.assertEqual(adapter.dispatch_guards, [("NODE-0", RELEASE_ID)])
        latest = [
            event
            for event in binding_events(self.root)
            if event["launch_instruction_id"] == instruction_id
        ][-1]
        self.assertEqual(latest["state"], "SUPERSEDED")

    def test_host_without_preparation_lifecycle_rejects_before_host_effects(self) -> None:
        contract = _contract(tasks=1)
        task = contract["tasks"][0]
        preparation = derive_launch_identity(
            execution_id=EXECUTION_ID,
            execution_namespace=EXECUTION_NAMESPACE,
            repository=str(task["repository"]),
            node_id=str(task["node_id"]),
            lifecycle=str(task["lifecycle"]),
            authority_class="PREPARATION_ONLY",
            branch=str(task["branch"]),
            target_branch=str(task["target_branch"]),
            target_sha=str(task["target_sha"]),
            plan_fingerprint=str(task["plan_fingerprint"]),
        )
        task["resource_key"] = preparation["resource_key"]
        task["launch_instruction_id"] = preparation["launch_instruction_id"]
        task["idempotency_key"] = preparation["launch_instruction_id"]
        task["authority_mode"] = "PREPARATION_ONLY"
        task["authority_class"] = "PREPARATION_ONLY"
        _rehash(contract)
        adapter = Adapter([])
        adapter.supports_preparation_only = False

        with self.assertRaisesRegex(
            HostExecutionError, "cannot observe preparation-only task lifecycle"
        ):
            execute_contract(self.root, contract, adapter, Resolver())

        self.assertEqual(adapter.created, [])
        self.assertEqual(binding_events(self.root), ())

    def test_persisted_event_replay_is_bounded(self) -> None:
        contract = _contract(tasks=1)
        instruction_id = str(contract["tasks"][0]["launch_instruction_id"])
        event = _event(instruction_id, "ACTIVE", "1")
        adapter = Adapter([[event], [event], [event]])
        result = execute_contract(
            self.root, contract, adapter, Resolver(), max_replay_events=2
        )
        self.assertEqual(result["blocker"]["code"], "HOST_REPLAY_LIMIT")

    def test_main_target_is_rejected_even_with_valid_contract_digest(self) -> None:
        contract = _contract(tasks=1)
        contract["target_branch"] = "main"
        contract["tasks"][0]["target_branch"] = "main"
        _rehash(contract)
        with self.assertRaisesRegex(HostExecutionError, "trusted singleton target"):
            execute_contract(self.root, contract, Adapter([]), Resolver())

    def test_external_host_target_must_match_control_plane(self) -> None:
        adapter = Adapter([])
        adapter.trusted_target = "release/other"
        with self.assertRaisesRegex(HostExecutionError, "host trust"):
            execute_contract(self.root, _contract(tasks=1), adapter, Resolver())

    def test_live_claim_and_lease_prevent_false_quiescence(self) -> None:
        contract = _contract(tasks=1)
        instruction_id = str(contract["tasks"][0]["launch_instruction_id"])
        adapter = Adapter([[_event(instruction_id, "SUCCEEDED", "1")]])
        adapter.runtime = {
            "target_branch": TARGET,
            "active_claims": ["OTHER-999"],
            "active_validation_lease": {"owner": "validator"},
            "quiescent": False,
        }
        result = execute_contract(self.root, contract, adapter, Resolver())
        self.assertEqual(result["outcome"], "ACTIVE")
        self.assertFalse(result["successful"])
        self.assertFalse(result["quiescent"])
        self.assertEqual(result["blocker"]["code"], "RUNTIME_AUTHORITY_ACTIVE")

    def test_retry_attempt_and_lineage_reach_durable_binding(self) -> None:
        first_id = str(_identity(0)["launch_instruction_id"])
        prepare_launch(self.root, first_id, "codex")
        bind_launch(
            self.root, first_id, "codex", "prior-task",
            host_id="host-1", cursor="prior-cursor", capability="prior-capability"
        )
        released = release_terminal_launch(
            self.root, first_id, host="codex", host_id="host-1", task_id="prior-task",
            cursor="prior-cursor", capability="prior-capability", terminal_state="FAILED",
            host_event_id="prior-terminal", host_event_cursor="prior-terminal-cursor"
        )
        contract = _contract(tasks=1)
        task = contract["tasks"][0]
        retry_identity = _identity(0, attempt=2, retry_of=str(released["event_id"]))
        task["attempt"] = 2
        task["retry_of"] = released["event_id"]
        task["resource_key"] = retry_identity["resource_key"]
        task["launch_instruction_id"] = retry_identity["launch_instruction_id"]
        task["idempotency_key"] = retry_identity["launch_instruction_id"]
        _rehash(contract)
        instruction_id = str(task["launch_instruction_id"])
        adapter = Adapter([[_event(instruction_id, "SUCCEEDED", "1")]])
        result = execute_contract(self.root, contract, adapter, Resolver())
        self.assertTrue(result["successful"])
        prepared = next(
            event for event in binding_events(self.root)
            if event["launch_instruction_id"] == instruction_id and event["state"] == "PREPARED"
        )
        self.assertEqual(prepared["attempt"], 2)
        self.assertEqual(prepared["retry_of"], released["event_id"])

    def test_sidecars_are_spawned_once_settle_and_notify_primary_before_success(self) -> None:
        contract = _sidecar_contract()
        instruction_id = str(contract["tasks"][0]["launch_instruction_id"])
        specs = contract["tasks"][0]["sidecars"]
        adapter = SidecarAdapter([
            {
                "primary_events": [_event(instruction_id, "SUCCEEDED", "1")],
                "sidecar_events": [
                    _sidecar_event(spec, "SUCCEEDED", "1", result=_sidecar_result(spec))
                    for spec in specs
                ],
            }
        ])
        adapter.contract = contract
        result = execute_contract(self.root, contract, adapter, Resolver())
        self.assertTrue(result["successful"])
        self.assertTrue(result["quiescent"])
        self.assertEqual(set(adapter.sidecar_spawned), {item["sidecar_id"] for item in specs})
        self.assertEqual(set(result["sidecar_terminal"].values()), {"SUCCEEDED"})
        self.assertGreaterEqual(len(adapter.messages), len(specs) * 2)
        self.assertEqual(active_sidecars(self.root), ())
    def test_primary_terminal_closes_unfinished_sidecars_and_parent_is_notified(self) -> None:
        contract = _sidecar_contract()
        instruction_id = str(contract["tasks"][0]["launch_instruction_id"])
        adapter = SidecarAdapter([{"primary_events": [_event(instruction_id, "SUCCEEDED", "1")], "sidecar_events": []}])
        adapter.contract = contract
        result = execute_contract(self.root, contract, adapter, Resolver())
        self.assertTrue(result["successful"])
        self.assertEqual(set(adapter.sidecar_closed), {item["sidecar_id"] for item in contract["tasks"][0]["sidecars"]})
        self.assertEqual(set(result["sidecar_terminal"].values()), {"CANCELLED"})
        self.assertEqual(active_sidecars(self.root), ())
        self.assertTrue(all(depth > 0 for _, depth in adapter.external_effects))
        self.assertTrue(
            {"create_thread", "spawn_sidecar", "send_message_to_thread", "close_sidecar"}
            <= {name for name, _ in adapter.external_effects}
        )

    def test_sidecar_binding_is_adopted_after_parent_restart(self) -> None:
        contract = _sidecar_contract()
        instruction_id = str(contract["tasks"][0]["launch_instruction_id"])
        specs = contract["tasks"][0]["sidecars"]
        adapter = SidecarAdapter([])
        adapter.contract = contract
        for spec in specs:
            adapter.spawn_sidecar(prompt=str(spec["prompt"]), token_budget=int(spec["token_budget"]), idempotency_key=str(spec["sidecar_id"]), parent_launch_instruction_id=instruction_id)
        adapter.sidecar_spawned.clear()
        adapter.activity_script = [{"primary_events": [_event(instruction_id, "SUCCEEDED", "1")], "sidecar_events": []}]
        result = execute_contract(self.root, contract, adapter, Resolver())
        self.assertTrue(result["successful"])
        self.assertEqual(adapter.sidecar_spawned, [])

    def test_over_budget_sidecar_terminal_is_rejected(self) -> None:
        contract = _sidecar_contract()
        instruction_id = str(contract["tasks"][0]["launch_instruction_id"])
        spec = contract["tasks"][0]["sidecars"][0]
        contract["tasks"][0]["sidecars"] = [spec]
        contract["sidecar_cohort"].update({
            "size": 1,
            "sidecar_ids": [spec["sidecar_id"]],
            "initial_host_reservations": 2,
            "remaining_descendant_slots": 6,
            "planned_token_budget": spec["token_budget"],
            "estimated_net_savings_tokens": spec["estimated_net_savings_tokens"],
        })
        _rehash(contract)
        adapter = SidecarAdapter([{"primary_events": [_event(instruction_id, "SUCCEEDED", "1")], "sidecar_events": [_sidecar_event(spec, "SUCCEEDED", "1", result=_sidecar_result(spec, usage=int(spec["token_budget"]) + 1))]}])
        adapter.contract = contract
        result = execute_contract(self.root, contract, adapter, Resolver())
        self.assertTrue(result["successful"])
        self.assertEqual(result["sidecar_terminal"][spec["sidecar_id"]], "FAILED")
        self.assertEqual(active_sidecars(self.root), ())

    def test_sidecar_may_request_but_only_root_spawns_a_budgeted_descendant(self) -> None:
        contract = _sidecar_contract()
        instruction_id = str(contract["tasks"][0]["launch_instruction_id"])
        parent = contract["tasks"][0]["sidecars"][0]
        request = {"purpose": "independent_review", "prompt": "Inspect receipt:child independently", "evidence_refs": ["receipt:child"]}
        child = make_descendant_spec(parent, request, contract["sidecar_cohort"]["policy"])
        other = contract["tasks"][0]["sidecars"][1:]
        adapter = SidecarAdapter([
            {"primary_events": [_event(instruction_id, "ACTIVE", "1")], "sidecar_events": [_sidecar_event(parent, "SPAWN_REQUEST", "1", request=request)]},
            {
                "primary_events": [_event(instruction_id, "SUCCEEDED", "2")],
                "sidecar_events": [
                    _sidecar_event(child, "SUCCEEDED", "1", result=_sidecar_result(child)),
                    _sidecar_event(parent, "SUCCEEDED", "2", result=_sidecar_result(parent)),
                    *[_sidecar_event(spec, "SUCCEEDED", "1", result=_sidecar_result(spec)) for spec in other],
                ],
            },
        ])
        adapter.contract = contract
        result = execute_contract(self.root, contract, adapter, Resolver())
        self.assertTrue(result["successful"])
        self.assertEqual(result["sidecar_terminal"][child["sidecar_id"]], "SUCCEEDED")
        self.assertIn(child["sidecar_id"], adapter.sidecar_spawned)
        self.assertTrue(any("ADMITTED" in message for message in adapter.sidecar_messages))
        self.assertTrue(all(depth > 0 for _, depth in adapter.external_effects))
        self.assertIn(
            "send_message_to_sidecar",
            {name for name, _ in adapter.external_effects},
        )

    def test_descendant_sidecar_is_denied_at_total_host_capacity(self) -> None:
        contract = _sidecar_contract(primary_tasks=6)
        self.assertEqual(
            len(contract["tasks"]) + int(contract["sidecar_cohort"]["size"]),
            8,
        )
        instruction_ids = [
            str(task["launch_instruction_id"]) for task in contract["tasks"]
        ]
        parent = contract["tasks"][0]["sidecars"][0]
        request = {
            "purpose": "independent_review",
            "prompt": "Inspect receipt:capacity independently",
            "evidence_refs": ["receipt:capacity"],
        }
        child = make_descendant_spec(
            parent, request, contract["sidecar_cohort"]["policy"]
        )
        adapter = SidecarAdapter(
            [
                {
                    "primary_events": [
                        _event(instruction_id, "ACTIVE", "1")
                        for instruction_id in instruction_ids
                    ],
                    "sidecar_events": [
                        _sidecar_event(parent, "SPAWN_REQUEST", "1", request=request)
                    ],
                },
                {
                    "primary_events": [
                        _event(instruction_id, "SUCCEEDED", "2")
                        for instruction_id in instruction_ids
                    ],
                    "sidecar_events": [
                        _sidecar_event(
                            spec,
                            "SUCCEEDED",
                            "2",
                            result=_sidecar_result(spec),
                        )
                        for spec in contract["tasks"][0]["sidecars"]
                    ],
                },
            ]
        )
        adapter.contract = contract

        result = execute_contract(self.root, contract, adapter, Resolver())

        self.assertTrue(result["successful"])
        self.assertNotIn(child["sidecar_id"], adapter.sidecar_spawned)
        self.assertEqual(len(adapter.created) + len(adapter.sidecar_spawned), 8)
        self.assertTrue(
            any(
                "DENIED: canonical attended host capacity exhausted" in message
                for message in adapter.sidecar_messages
            )
        )
        self.assertTrue(all(depth > 0 for _, depth in adapter.external_effects))

    def test_sidecar_ledger_corruption_fails_closed(self) -> None:
        path = self.root / ".autopilot" / "state" / "sidecar-bindings.jsonl"
        from sidecar_execution import record_sidecar_state

        record_sidecar_state(
            self.root,
            "sha256:" + "c" * 64,
            "PREPARED",
            parent_launch_instruction_id="sha256:" + "d" * 64,
        )
        path.write_text('{"broken":', encoding="utf-8")
        with self.assertRaisesRegex(Exception, "sidecar ledger line 1 is invalid"):
            sidecar_events(self.root)

    def test_blocking_combined_wait_times_out_and_settles_every_sidecar(self) -> None:
        contract = _sidecar_contract()
        contract["sidecar_cohort"]["policy"]["wait_timeout_seconds"] = 1
        _rehash(contract)
        adapter = SidecarAdapter([])
        adapter.contract = contract

        def blocked_wait(primary_targets, sidecar_targets):
            del primary_targets, sidecar_targets
            time.sleep(2)
            return {"primary_events": [], "sidecar_events": []}

        adapter.wait_activity = blocked_wait  # type: ignore[method-assign]
        started = time.monotonic()
        result = execute_contract(self.root, contract, adapter, Resolver())
        self.assertLess(time.monotonic() - started, 1.8)
        self.assertEqual(result["blocker"]["code"], "SIDECAR_WAIT_TIMEOUT")
        self.assertEqual(active_sidecars(self.root), ())


class HostEffectAmbiguityTests(unittest.TestCase):
    def test_real_app_server_adapter_adopts_accepted_create_without_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plane = app_server_fixture.FakePlane(root)
            executable = root / "codex.exe"
            executable.write_bytes(b"fake-codex-0.146.0")
            server = app_server_fixture.FakeAppServer()
            adapter = app_server_fixture.app_server_host.CodexAppServerHost(
                plane=plane,
                host_id=None,
                execution_namespace=plane.execution_namespace,
                execution_id=plane.execution_id,
                execution_dir=plane.execution_dir,
                host_runtime_dir=plane.host_runtime_dir,
                wait_seconds=1,
                adapter_module_digest=app_server_fixture.digest_bytes(
                    app_server_fixture.MODULE_PATH.read_bytes()
                ),
                executable_path=executable,
                process_factory=server.process_factory,
                version_probe=lambda _path, _environment: "codex-cli 0.146.0",
                schema_probe=lambda _path, _environment: {
                    "schema_bundle_digest": app_server_fixture.digest_text("bundle"),
                    "thread_start_schema_digest": app_server_fixture.digest_text(
                        "thread/start"
                    ),
                    "turn_start_schema_digest": app_server_fixture.digest_text(
                        "turn/start"
                    ),
                },
                environment={"PATH": "isolated-path", "SYSTEMROOT": "C:\\Windows"},
                clock=lambda: datetime(2026, 8, 14, 12, 0, tzinfo=UTC),
            )
            self.addCleanup(adapter.close)
            (plane.execution_dir / "locks").mkdir(exist_ok=True)
            controller_module.atomic_write_json(
                plane.execution_dir / "execution-identity.json",
                {
                    "namespace": plane.execution_namespace,
                    "execution_id": plane.execution_id,
                },
            )
            binding = _synthetic_effect_fence()
            idempotency_key = app_server_fixture.digest_text("accepted-create")
            attempts = 0

            def accepted_then_lost() -> Mapping[str, object]:
                nonlocal attempts
                attempts += 1
                adapter.create_thread(
                    title="Managed integration task",
                    prompt="Exercise exact host-effect reconciliation.",
                    idempotency_key=idempotency_key,
                )
                raise TimeoutError("response lost after App Server acceptance")

            @contextmanager
            def admitted(*_args: object, **_kwargs: object):
                yield None

            with mock.patch.object(
                host_execution_module, "_effect_guard", admitted
            ), mock.patch.object(
                host_execution_module,
                "require_host_runtime",
                return_value=plane.host_runtime_dir,
            ), mock.patch.object(
                host_execution_module,
                "_execution_adapter_snapshot",
                return_value={"record_id": "sha256:" + "8" * 64},
            ), mock.patch.object(
                host_execution_module,
                "_validate_effect_adapter_fence",
                return_value={"record_id": "sha256:" + "8" * 64},
            ):
                with self.assertRaises(TimeoutError):
                    host_execution_module._perform_host_effect(
                        plane.repo_root,
                        binding,
                        plane.execution_dir,
                        adapter=adapter,
                        effect_kind="CREATE_THREAD",
                        idempotency_key=idempotency_key,
                        request={"title": "Managed integration task"},
                        operation=accepted_then_lost,
                    )
                adopted = host_execution_module._perform_host_effect(
                    plane.repo_root,
                    binding,
                    plane.execution_dir,
                    adapter=adapter,
                    effect_kind="CREATE_THREAD",
                    idempotency_key=idempotency_key,
                    request={"title": "Managed integration task"},
                    operation=accepted_then_lost,
                )
            self.assertEqual(attempts, 1)
            self.assertEqual(adopted["idempotency_key"], idempotency_key)
            self.assertEqual(
                host_execution_module._host_effect_events(
                    plane.execution_dir, binding.instruction_id
                )[-1]["state"],
                "COMPLETED",
            )

    def test_reconciliation_rejects_nested_identity_and_outcome_corruption(self) -> None:
        execution_id = "sha256:" + "9" * 64
        effect_id = "sha256:" + "4" * 64
        host_id = "app-server:fixture"
        effect = {
            "effect_kind": "CREATE_THREAD",
            "idempotency_key": effect_id,
            **_synthetic_effect_provenance(),
        }

        def sealed(material: Mapping[str, object]) -> dict[str, object]:
            return {
                **dict(material),
                "record_id": host_execution_module.digest_json(material),
            }

        def external(external_id: str | None = "thread:fixture") -> dict[str, object]:
            return sealed(
                {
                    "schema_version": 1,
                    "kind": "hive-mind-host-effect-external-identity-v1",
                    "execution_namespace": "default",
                    "execution_id": execution_id,
                    "host_id": host_id,
                    "effect_kind": "CREATE_THREAD",
                    "idempotency_key": effect_id,
                    "external_id": external_id,
                }
            )

        def unresolved(identity: str = "thread:unknown") -> dict[str, object]:
            return sealed(
                {
                    "schema_version": 1,
                    "kind": "hive-mind-unobserved-host-lifecycle-item-v1",
                    "execution_namespace": "default",
                    "execution_id": execution_id,
                    "host_id": host_id,
                    "effect_kind": "CREATE_THREAD",
                    "idempotency_key": effect_id,
                    "item_type": "THREAD",
                    "item_identity": identity,
                }
            )

        def observation(
            *,
            outcome: str = "COMPLETED",
            external_identity: Mapping[str, object] | None = None,
            result: Mapping[str, object] | None = None,
            unobserved: list[Mapping[str, object]] | None = None,
        ) -> dict[str, object]:
            return sealed(
                {
                    "schema_version": 1,
                    "kind": "hive-mind-host-effect-reconciliation-observation-v1",
                    "execution_namespace": "default",
                    "execution_id": execution_id,
                    "host_id": host_id,
                    "effect_kind": "CREATE_THREAD",
                    "idempotency_key": effect_id,
                    "outcome": outcome,
                    "external_identity": dict(external_identity or external()),
                    "result": (
                        {"accepted": True} if result is None and outcome == "COMPLETED" else result
                    ),
                    "unobserved_host_lifecycle_items": list(unobserved or []),
                    "observed_at": "2030-01-01T00:00:01Z",
                }
            )

        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary)
            controller_module.atomic_write_json(
                state_dir / "execution-identity.json",
                {"namespace": "default", "execution_id": execution_id},
            )
            valid = observation()
            validated = host_execution_module._validate_effect_reconciliation(
                valid,
                effect=effect,
                state_dir=state_dir,
                expected_host_id=host_id,
            )
            self.assertEqual(validated["adapter_observation_id"], valid["record_id"])
            for field, expected in _synthetic_effect_provenance().items():
                self.assertEqual(validated[field], expected)
            wrong_host_material = dict(external())
            wrong_host_material.pop("record_id")
            wrong_host_material["host_id"] = "app-server:other"
            wrong_host = observation(external_identity=sealed(wrong_host_material))
            completed_with_unknown = observation(unobserved=[unresolved()])
            unknown_with_result = observation(
                outcome="UNKNOWN",
                external_identity=external(None),
                result={"accepted": True},
                unobserved=[unresolved()],
            )
            unknown_without_obligation = observation(
                outcome="UNKNOWN",
                external_identity=external(None),
                result=None,
                unobserved=[],
            )
            duplicate_obligation = observation(
                outcome="UNKNOWN",
                external_identity=external(None),
                result=None,
                unobserved=[unresolved(), unresolved()],
            )
            for label, corrupted in (
                ("nested host mutation", wrong_host),
                ("completed unresolved item", completed_with_unknown),
                ("unknown fabricated result", unknown_with_result),
                ("unknown missing obligation", unknown_without_obligation),
                ("duplicate unresolved item", duplicate_obligation),
            ):
                with self.subTest(label=label), self.assertRaises(HostExecutionError):
                    host_execution_module._validate_effect_reconciliation(
                        corrupted,
                        effect=effect,
                        state_dir=state_dir,
                        expected_host_id=host_id,
                    )

    def test_ambiguous_external_write_is_never_automatically_reissued(self) -> None:
        effect_kinds = (
            "CREATE_THREAD",
            "SEND_PRIMARY_MESSAGE",
            "SPAWN_SIDECAR",
            "SEND_SIDECAR_MESSAGE",
            "CLOSE_SIDECAR",
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "locks").mkdir(parents=True)
            binding = _synthetic_effect_fence()

            class AmbiguousAdapter:
                host_runtime_dir = root
                host_id = "app-server:fixture"

            adapter = AmbiguousAdapter()

            @contextmanager
            def admitted(*_args: object, **_kwargs: object):
                yield None

            for index, effect_kind in enumerate(effect_kinds, 4):
                with self.subTest(effect_kind=effect_kind):
                    state_dir = root / str(index)
                    (state_dir / "locks").mkdir(parents=True)
                    attempts = 0

                    def ambiguous() -> Mapping[str, object]:
                        nonlocal attempts
                        attempts += 1
                        raise TimeoutError("response lost after external acceptance")

                    with mock.patch.object(
                        host_execution_module, "_effect_guard", admitted
                    ), mock.patch.object(
                        host_execution_module,
                        "utc_now",
                        return_value=datetime(2030, 1, 1, tzinfo=UTC),
                    ), mock.patch.object(
                        host_execution_module,
                        "require_host_runtime",
                        return_value=root,
                    ), mock.patch.object(
                        host_execution_module,
                        "_execution_adapter_snapshot",
                        return_value={"record_id": "sha256:" + "8" * 64},
                    ), mock.patch.object(
                        host_execution_module,
                        "_validate_effect_adapter_fence",
                        return_value={"record_id": "sha256:" + "8" * 64},
                    ):
                        with self.assertRaises(TimeoutError):
                            host_execution_module._perform_host_effect(
                                root,
                                binding,
                                state_dir,
                                adapter=adapter,
                                effect_kind=effect_kind,
                                idempotency_key="sha256:" + str(index) * 64,
                                request={"operation": effect_kind},
                                operation=ambiguous,
                            )
                        with self.assertRaisesRegex(
                            HostExecutionError, "ambiguous external outcome"
                        ):
                            host_execution_module._perform_host_effect(
                                root,
                                binding,
                                state_dir,
                                adapter=adapter,
                                effect_kind=effect_kind,
                                idempotency_key="sha256:" + str(index) * 64,
                                request={"operation": effect_kind},
                                operation=ambiguous,
                            )
                    self.assertEqual(attempts, 1)
                    states = [
                        event["state"]
                        for event in host_execution_module._host_effect_events(
                            state_dir, binding.instruction_id
                        )
                    ]
                    self.assertEqual(states, ["PREPARED", "RECONCILIATION_REQUIRED"])

    def test_authenticated_reconciliation_adopts_every_ambiguous_effect(self) -> None:
        effect_kinds = (
            "CREATE_THREAD",
            "SEND_PRIMARY_MESSAGE",
            "SPAWN_SIDECAR",
            "SEND_SIDECAR_MESSAGE",
            "CLOSE_SIDECAR",
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binding = _synthetic_effect_fence()

            @contextmanager
            def admitted(*_args: object, **_kwargs: object):
                yield None

            class Reconciler:
                host_id = "app-server:fixture"
                host_runtime_dir = root

                def read_effect_reconciliation(
                    self, *, effect_kind: str, idempotency_key: str
                ) -> Mapping[str, object]:
                    result = {"effect_kind": effect_kind, "accepted": True}
                    external_material = {
                        "schema_version": 1,
                        "kind": "hive-mind-host-effect-external-identity-v1",
                        "execution_namespace": "default",
                        "execution_id": "sha256:" + "9" * 64,
                        "host_id": self.host_id,
                        "effect_kind": effect_kind,
                        "idempotency_key": idempotency_key,
                        "external_id": "thread:fixture",
                    }
                    material = {
                        "schema_version": 1,
                        "kind": "hive-mind-host-effect-reconciliation-observation-v1",
                        "execution_namespace": "default",
                        "execution_id": "sha256:" + "9" * 64,
                        "host_id": self.host_id,
                        "effect_kind": effect_kind,
                        "idempotency_key": idempotency_key,
                        "outcome": "COMPLETED",
                        "external_identity": {
                            **external_material,
                            "record_id": host_execution_module.digest_json(
                                external_material
                            ),
                        },
                        "result": result,
                        "unobserved_host_lifecycle_items": [],
                        "observed_at": "2030-01-01T00:00:01Z",
                    }
                    return {
                        **material,
                        "record_id": host_execution_module.digest_json(material),
                    }

            for index, effect_kind in enumerate(effect_kinds, 4):
                with self.subTest(effect_kind=effect_kind):
                    state_dir = root / str(index)
                    (state_dir / "locks").mkdir(parents=True)
                    controller_module.atomic_write_json(
                        state_dir / "execution-identity.json",
                        {
                            "namespace": "default",
                            "execution_id": "sha256:" + "9" * 64,
                        },
                    )
                    calls = 0

                    def ambiguous() -> Mapping[str, object]:
                        nonlocal calls
                        calls += 1
                        raise TimeoutError("accepted before response loss")

                    with mock.patch.object(
                        host_execution_module, "_effect_guard", admitted
                    ), mock.patch.object(
                        host_execution_module,
                        "utc_now",
                        return_value=datetime(2030, 1, 1, tzinfo=UTC),
                    ), mock.patch.object(
                        host_execution_module,
                        "require_host_runtime",
                        return_value=root,
                    ), mock.patch.object(
                        host_execution_module,
                        "_execution_adapter_snapshot",
                        return_value={"record_id": "sha256:" + "8" * 64},
                    ), mock.patch.object(
                        host_execution_module,
                        "_validate_effect_adapter_fence",
                        return_value={"record_id": "sha256:" + "8" * 64},
                    ):
                        with self.assertRaises(TimeoutError):
                            host_execution_module._perform_host_effect(
                                root,
                                binding,
                                state_dir,
                                adapter=Reconciler(),
                                effect_kind=effect_kind,
                                idempotency_key="sha256:" + str(index) * 64,
                                request={"operation": effect_kind},
                                operation=ambiguous,
                            )
                        adopted = host_execution_module._perform_host_effect(
                            root,
                            binding,
                            state_dir,
                            adapter=Reconciler(),
                            effect_kind=effect_kind,
                            idempotency_key="sha256:" + str(index) * 64,
                            request={"operation": effect_kind},
                            operation=ambiguous,
                        )
                    self.assertEqual(adopted["effect_kind"], effect_kind)
                    self.assertEqual(calls, 1)
                    self.assertEqual(
                        host_execution_module._host_effect_events(
                            state_dir, binding.instruction_id
                        )[-1]["state"],
                        "COMPLETED",
                    )


if __name__ == "__main__":
    unittest.main()
