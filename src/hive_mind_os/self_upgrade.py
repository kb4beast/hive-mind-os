"""Immutable runtime challengers and host-broker-mediated activation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

from .brain_kernel.canonical import canonical_digest


class UpgradeDecision(str, Enum):
    RETAIN = "RETAIN"
    CANARY = "CANARY"
    PROMOTE = "PROMOTE"
    ROLLBACK = "ROLLBACK"
    DEFER = "DEFER"
    QUARANTINE = "QUARANTINE"


@dataclass(frozen=True, slots=True)
class RuntimeChallenger:
    version: str
    artifact_digest: str
    champion_parent: str
    source_ref: str
    dependency_manifest: str
    migration_manifest: str
    rollback_artifact: str
    evaluation_plan: str
    evaluation_result: str | None
    builder_id: str
    evaluator_id: str
    judge_id: str
    canary_scope: str

    @property
    def digest(self):
        return canonical_digest(self)

    def __post_init__(self):
        if not all(
            (
                self.version,
                self.artifact_digest,
                self.champion_parent,
                self.source_ref,
                self.dependency_manifest,
                self.migration_manifest,
                self.rollback_artifact,
                self.evaluation_plan,
                self.builder_id,
                self.evaluator_id,
                self.judge_id,
                self.canary_scope,
            )
        ):
            raise ValueError("challenger manifest is incomplete")
        if not self.artifact_digest.startswith("sha256:"):
            raise ValueError("artifact digest must be canonical")


@dataclass(frozen=True, slots=True)
class UpgradeReceipt:
    decision: UpgradeDecision
    challenger_digest: str
    reason: str
    activation_digest: str | None = None


class HostBroker(Protocol):
    def activate(self, challenger: RuntimeChallenger) -> str: ...
    def rollback(self, challenger: RuntimeChallenger) -> str: ...


class UpgradeController:
    def __init__(
        self,
        host: HostBroker | None = None,
        *,
        state_path: str | Path | None = None,
    ):
        self.host = host
        self.state_path = Path(state_path) if state_path is not None else None
        self.active: RuntimeChallenger | None = None
        self.active_digest: str | None = None
        self.pending_digest: str | None = None
        self.state = "CHAMPION_ACTIVE"
        self.previous: str | None = None
        self._load()

    def _load(self) -> None:
        if self.state_path is None or not self.state_path.exists():
            return
        value = json.loads(self.state_path.read_text(encoding="utf-8"))
        if set(value) != {"state", "active_digest", "pending_digest", "previous"}:
            raise ValueError("invalid upgrade controller state")
        self.state = value["state"]
        self.active_digest = value["active_digest"]
        self.pending_digest = value["pending_digest"]
        self.previous = value["previous"]

    def _persist(self) -> None:
        if self.state_path is None:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        body = json.dumps(
            {
                "active_digest": self.active_digest,
                "pending_digest": self.pending_digest,
                "previous": self.previous,
                "state": self.state,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(body + "\n", encoding="utf-8")
        temporary.replace(self.state_path)

    def decide(
        self,
        c: RuntimeChallenger,
        *,
        qualification_passed: bool,
        heldout_passed: bool,
        rollback_valid: bool,
    ) -> UpgradeReceipt:
        if c.builder_id in {c.evaluator_id, c.judge_id} or c.evaluator_id == c.judge_id:
            return UpgradeReceipt(
                UpgradeDecision.QUARANTINE,
                c.digest,
                "identity roles are not independent",
            )
        if not qualification_passed or not heldout_passed:
            return UpgradeReceipt(
                UpgradeDecision.RETAIN,
                c.digest,
                "qualification or held-out evaluation incomplete",
            )
        if not rollback_valid:
            return UpgradeReceipt(
                UpgradeDecision.QUARANTINE, c.digest, "rollback artifact is invalid"
            )
        if self.host is None:
            return UpgradeReceipt(
                UpgradeDecision.CANARY,
                c.digest,
                "host activation authority unavailable",
            )
        try:
            self.state = "CANARY_PREPARED"
            self.pending_digest = c.digest
            self._persist()
            activation = self.host.activate(c)
            if type(activation) is not str or not activation.strip():
                raise ValueError("host returned no activation receipt")
            self.active = c
            self.active_digest = c.digest
            self.pending_digest = None
            self.previous = c.champion_parent
            self.state = "CHAMPION_ACTIVE"
            self._persist()
            return UpgradeReceipt(
                UpgradeDecision.PROMOTE,
                c.digest,
                "independent verdict accepted",
                activation,
            )
        except PermissionError:
            return UpgradeReceipt(
                UpgradeDecision.CANARY,
                c.digest,
                "host activation authority unavailable",
            )
        except (TimeoutError, ConnectionError):
            self.state = "RECONCILIATION_REQUIRED"
            self._persist()
            return UpgradeReceipt(
                UpgradeDecision.DEFER,
                c.digest,
                "activation outcome requires reconciliation",
            )

    def reconcile(self, c: RuntimeChallenger) -> UpgradeReceipt:
        if self.pending_digest != c.digest or self.state != "RECONCILIATION_REQUIRED":
            return UpgradeReceipt(
                UpgradeDecision.QUARANTINE,
                c.digest,
                "no matching uncertain activation",
            )
        observer = getattr(self.host, "observe", None)
        if not callable(observer):
            return UpgradeReceipt(
                UpgradeDecision.DEFER,
                c.digest,
                "host cannot observe the uncertain activation",
            )
        activation = observer(c)
        if type(activation) is not str or not activation.strip():
            return UpgradeReceipt(
                UpgradeDecision.DEFER,
                c.digest,
                "active version pointer is not yet observed",
            )
        self.active = c
        self.active_digest = c.digest
        self.pending_digest = None
        self.previous = c.champion_parent
        self.state = "CHAMPION_ACTIVE"
        self._persist()
        return UpgradeReceipt(
            UpgradeDecision.PROMOTE,
            c.digest,
            "activation reconciled from the host pointer",
            activation,
        )

    def rollback(self, c: RuntimeChallenger) -> UpgradeReceipt:
        if self.host is None:
            return UpgradeReceipt(
                UpgradeDecision.DEFER, c.digest, "host activation authority unavailable"
            )
        if self.active_digest != c.digest:
            return UpgradeReceipt(
                UpgradeDecision.QUARANTINE,
                c.digest,
                "challenger is not the observed active version",
            )
        activation = self.host.rollback(c)
        self.active = None
        self.active_digest = None
        self.pending_digest = None
        self.state = "CHAMPION_ACTIVE"
        self._persist()
        return UpgradeReceipt(
            UpgradeDecision.ROLLBACK, c.digest, "rollback requested", activation
        )
