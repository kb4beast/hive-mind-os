"""Deterministic local adapter for the canonical kernel mission runtime."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ...brain_kernel.authority import AuthorityRegistry
from ...brain_kernel.canonical import canonical_digest
from ...brain_kernel.consultation import (
    ConsultationDecision,
    ConsultationReason,
    ConsultationRequest,
    RoleAssessment,
)
from ...brain_kernel.contracts import Budget, ConstraintEnvelope, EffectIntent
from ...brain_kernel.effect_outbox import DurableEffectOutbox
from ...brain_kernel.effects import EffectGateway, sealed_intent
from ...brain_kernel.mission_runtime import (
    BuilderEffectBinding,
    MissionBindings,
    MissionConfig,
    MissionRunReceipt,
    MissionRuntime,
    WorkVerificationSpec,
)
from ...brain_kernel.reconciler import RepairAction, RepairKind
from ...brain_kernel.roles import KERNEL_IMPLEMENTED_ROLES
from ...brain_kernel.store import KernelStore
from .local_execution import LocalWorkspaceAdapter
from .role_handlers import RepositoryRoleHandlers

_Z = "sha256:" + "0" * 64
_SHA = "0" * 40
_TIME = "2026-08-11T00:00:00Z"
_AUTH_TIME = "2029-01-01T00:00:00Z"


class MissionAdapterError(RuntimeError):
    """The deterministic local mission fixture cannot be constructed safely."""


class _DeterministicEffectGateway(EffectGateway):
    """A store-backed gateway built with authority=registry and an injected clock.

    ``EffectGateway`` constructs its ``DurableEffectOutbox`` with the default
    wall clock, and a receipt's ``started_at``/``ended_at`` are inside
    ``receipt_digest`` — which reaches the mission's event head through the
    builder's ``role.result``.  Two runs of the same fixture would therefore
    never agree on ``event_head_digest``, which this node's replay evidence
    requires them to.

    The injectable clock already exists on ``DurableEffectOutbox``; this only
    supplies it.  Widening ``EffectGateway`` to take a clock would be the
    tidier home for this, but ``brain_kernel/effects.py`` belongs to EFFECT-220
    and is outside this node's write scope, so the seam is supplied here rather
    than by editing another node's file.  The override hands the outbox the
    issuing registry and the adapter host table, so the boundary this gateway
    would have applied is applied by the outbox instead of being skipped.
    """

    def __init__(
        self, store: KernelStore, *, now: str, authority: AuthorityRegistry, authorized_at: str
    ) -> None:
        super().__init__(store, authority=authority, clock=lambda: authorized_at)
        self._kernel_store = store
        self._now = now
        self._registry = authority
        self._authorized_at = authorized_at
        self._bound: dict[str, Callable[[EffectIntent], None]] = {}
        self._bound_versions: dict[str, str] = {}
        self._bound_hosts: dict[str, tuple[str, ...]] = {}

    def register_adapter(
        self,
        name: str,
        adapter: Callable[[EffectIntent], None],
        *,
        version: str = "1",
        network_hosts: tuple[str, ...] = (),
    ) -> None:
        super().register_adapter(name, adapter, version=version, network_hosts=network_hosts)
        self._bound[name] = adapter
        self._bound_versions[name] = version
        self._bound_hosts[name] = tuple(network_hosts)

    def execute(self, intent: EffectIntent, token):
        return DurableEffectOutbox(
            self._kernel_store,
            adapters=self._bound,
            adapter_versions=self._bound_versions,
            adapter_hosts=self._bound_hosts,
            authority=self._registry,
            clock=lambda: self._now,
        ).execute(intent, token)


@dataclass(slots=True)
class LocalMissionEnvironment:
    """Owns the local state used by one canonical mission fixture."""

    root: Path
    store: KernelStore
    workspace: LocalWorkspaceAdapter
    registry: AuthorityRegistry
    gateway: EffectGateway
    config: MissionConfig
    bindings: MissionBindings
    bundle_directories: dict[str, Path]
    released_leases: list[str] = field(default_factory=list)
    retried_work: list[str] = field(default_factory=list)

    def close(self) -> None:
        self.store.close()


def _work_id(mission_id: str, role: str) -> str:
    return f"WORK-{mission_id.removeprefix('MISSION-')}-{role}"


def _attempt_id(mission_id: str, role: str) -> str:
    return f"ATTEMPT-{mission_id.removeprefix('MISSION-')}-{role}"


def build_local_mission_environment(
    root: str | Path, *, mission_suffix: str = "local", store: KernelStore | None = None,
) -> LocalMissionEnvironment:
    root_path = Path(root).resolve()
    root_path.mkdir(parents=True, exist_ok=True)
    mission_id = f"MISSION-{mission_suffix}"
    builder_work_id = _work_id(mission_id, "builder")
    builder_attempt_id = _attempt_id(mission_id, "builder")
    base = root_path / "base"
    base.mkdir(parents=True, exist_ok=True)
    (base / "app.txt").write_text("before\n", encoding="utf-8")
    workspace = LocalWorkspaceAdapter(root_path)
    candidate = root_path / "candidate"
    if not candidate.exists():
        workspace.materialize(base, "candidate")
    kernel_store = store or KernelStore(root_path / "kernel.sqlite3")
    registry = AuthorityRegistry()
    envelope = ConstraintEnvelope(
        f"AUTH-mission-{mission_suffix}", mission_id, builder_work_id, None, "builder", "R1",
        ("write",), ("network", "push", "merge", "deploy"), ("candidate",), ("candidate",),
        (), (), (), (), Budget(1, 0, 0, 0, 0, 1, 1, 1), "2030-01-01T00:00:00Z", _Z, _Z,
    ).sealed()
    registry.mint_root(
        envelope,
        issuer=f"mission:{mission_suffix}:fixture-owner",
        authority_ref="local-mission-policy",
        recorded_at=_TIME,
    )
    gateway = _DeterministicEffectGateway(
        kernel_store, now=_TIME, authority=registry, authorized_at=_AUTH_TIME
    )
    gateway.register_adapter("isolated-write", workspace.apply)
    parameters_digest = workspace.register_payload(b"after\n")
    intent = sealed_intent(EffectIntent(
        mission_id, builder_work_id, builder_attempt_id, "mission:builder", "builder", "write", "R1",
        "isolated-write", "candidate/app.txt", parameters_digest,
        canonical_digest({"mission": mission_id, "effect": "builder-write"}), envelope.digest_value, (),
        "discard isolated candidate", "local-mission-policy", canonical_digest({"intent": mission_id}),
    ))
    specs: dict[str, WorkVerificationSpec] = {}
    directories: dict[str, Path] = {}
    for role in KERNEL_IMPLEMENTED_ROLES:
        work_id = _work_id(mission_id, role)
        bundle_ref = f"bundle:{work_id}"
        bundle_directory = root_path / "bundles" / work_id
        directories[bundle_ref] = bundle_directory
        check_runner: Callable[..., bool]
        if role == "builder":
            def _builder_check(command: str, _candidate: Path, expected: Path = candidate) -> bool:
                return command == "local-check" and (expected / "app.txt").read_text(encoding="utf-8") == "after\n"
            check_runner = _builder_check
            base_root = str(base)
        else:
            def _default_check(command: str, _candidate: Path) -> bool:
                return command == "local-check"
            check_runner = _default_check
            base_root = str(candidate)
        specs[role] = WorkVerificationSpec(
            base_root, str(candidate), ("local-check",), ("app.txt",), check_runner,
            str(bundle_directory), bundle_ref,
        )
    request = ConsultationRequest(
        f"CONSULT-{mission_suffix}-1", mission_id,
        "Which exact candidate content satisfies the acceptance check?",
        ConsultationReason.AMBIGUOUS_DESIGN, "builder", ("curator", "integrator"),
    )
    assessments = (
        RoleAssessment("curator", "mission:curator:consult", "write after\\n to candidate/app.txt",
                       ("fixture:consultation-evidence",), ConsultationDecision.RESOLVED),
        RoleAssessment("integrator", "mission:integrator:consult", "write after\\n to candidate/app.txt",
                       ("fixture:consultation-evidence",), ConsultationDecision.RESOLVED),
    )
    config = MissionConfig(
        mission_id, "run one canonical local mission", "canonical-mission-runtime",
        "local-fixture", _SHA, "candidate/local-mission", _TIME,
        Budget(400, 16, 800, 800, 800, 40, 12, 4), Budget(50, 2, 100, 100, 100, 5, 1, 1),
    )
    bindings = MissionBindings(
        RepositoryRoleHandlers(),
        BuilderEffectBinding(registry, gateway, envelope.digest_value, intent, _AUTH_TIME),
        specs, request, assessments,
    )
    return LocalMissionEnvironment(root_path, kernel_store, workspace, registry, gateway, config,
                                   bindings, directories)


def run_local_mission(root: str | Path, *, mission_suffix: str = "local") -> tuple[MissionRunReceipt, LocalMissionEnvironment]:
    environment = build_local_mission_environment(root, mission_suffix=mission_suffix)
    return MissionRuntime(environment.store).run(environment.config, environment.bindings), environment


def rebuild_candidate_workspace(environment: LocalMissionEnvironment) -> Path:
    candidate = environment.root / "candidate"
    if candidate.exists():
        raise MissionAdapterError("candidate workspace already exists")
    return environment.workspace.materialize(environment.root / "base", "candidate")


def repair_handlers(environment: LocalMissionEnvironment) -> dict[RepairKind, Callable[[RepairAction], None]]:
    def rebuild(action: RepairAction) -> None:
        if action.target_id != "candidate":
            raise MissionAdapterError("only the recorded candidate workspace can be rebuilt")
        candidate = environment.root / "candidate"
        if candidate.exists():
            shutil.rmtree(candidate)
        rebuild_candidate_workspace(environment)

    def release(action: RepairAction) -> None:
        environment.released_leases.append(action.target_id)

    def retry(action: RepairAction) -> None:
        environment.retried_work.append(action.target_id)

    return {
        RepairKind.REBUILD_WORKSPACE: rebuild,
        RepairKind.RELEASE_STALE_LEASE: release,
        RepairKind.RETRY: retry,
    }


__all__ = [
    "LocalMissionEnvironment", "MissionAdapterError", "build_local_mission_environment",
    "rebuild_candidate_workspace", "repair_handlers", "run_local_mission",
]
