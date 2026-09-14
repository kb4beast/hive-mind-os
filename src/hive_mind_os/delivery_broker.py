"""Separate, grant-checked delivery boundary for qualified artifacts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from .brain_kernel.canonical import canonical_digest


class DeliveryState(str, Enum):
    LOCAL_ARTIFACT_READY = "LOCAL_ARTIFACT_READY"
    PUSH_PENDING = "PUSH_PENDING"
    PR_PENDING = "PR_PENDING"
    PUBLISHED = "PUBLISHED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    BLOCKED = "BLOCKED"


class ArtifactKind(str, Enum):
    APPLICATION = "application"
    LESSONS_ONLY = "lessons-only"


@dataclass(frozen=True, slots=True)
class DeliveryRequest:
    request_id: str
    package_id: str
    tenant_id: str
    candidate_commit: str
    candidate_tree: str
    qualification_digest: str
    target: str
    base: str
    run_branch: str
    grant_ref: str
    artifact_kind: ArtifactKind
    content_digest: str
    idempotency_key: str
    changed_paths: tuple[str, ...] = ()

    def __post_init__(self):
        if not all(
            (
                self.request_id,
                self.package_id,
                self.tenant_id,
                self.candidate_commit,
                self.target,
                self.base,
                self.run_branch,
                self.idempotency_key,
            )
        ):
            raise ValueError("delivery identity is required")
        if self.run_branch in {self.base, "main", "master"}:
            raise ValueError("protected branch cannot be a run branch")


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    state: DeliveryState
    request_digest: str
    branch_head: str | None = None
    pr_id: str | None = None
    blocker: str | None = None


@dataclass(frozen=True, slots=True)
class DeliveryGrant:
    grant_ref: str
    tenant_id: str
    target: str
    base: str
    branch_prefix: str
    artifact_kinds: tuple[ArtifactKind, ...]
    allowed_actions: tuple[str, ...] = ("push", "draft_pr")
    revoked: bool = False

    def allows(self, request: DeliveryRequest) -> bool:
        return (
            not self.revoked
            and request.grant_ref == self.grant_ref
            and request.tenant_id == self.tenant_id
            and request.target == self.target
            and request.base == self.base
            and request.run_branch.startswith(self.branch_prefix)
            and request.artifact_kind in self.artifact_kinds
            and {"push", "draft_pr"}.issubset(self.allowed_actions)
        )


class DeliveryTransport(Protocol):
    def push(self, branch: str, commit: str) -> str: ...
    def find_or_create_draft(
        self, branch: str, base: str, title: str, body: str
    ) -> str: ...


class DeliveryBroker:
    def __init__(
        self,
        transport: DeliveryTransport | None = None,
        *,
        grants: dict[str, Any] | None = None,
        state_path: str | Path | None = None,
    ):
        self.transport = transport
        self.grants = grants or {}
        self.state_path = Path(state_path) if state_path is not None else None
        self.results: dict[str, tuple[str, DeliveryResult]] = {}
        self._load()

    def _load(self):
        if self.state_path is None or not self.state_path.exists():
            return
        document = json.loads(self.state_path.read_text(encoding="utf-8"))
        for key, item in document.items():
            self.results[key] = (
                item["request_digest"],
                DeliveryResult(
                    DeliveryState(item["state"]),
                    item["request_digest"],
                    item.get("branch_head"),
                    item.get("pr_id"),
                    item.get("blocker"),
                ),
            )

    def _record(self, key: str, digest: str, result: DeliveryResult):
        self.results[key] = (digest, result)
        if self.state_path is not None:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            body = {
                item_key: {
                    "request_digest": item_digest,
                    "state": item_result.state.value,
                    "branch_head": item_result.branch_head,
                    "pr_id": item_result.pr_id,
                    "blocker": item_result.blocker,
                }
                for item_key, (item_digest, item_result) in sorted(self.results.items())
            }
            temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
            temporary.write_text(
                json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            temporary.replace(self.state_path)
        return result

    def prepare(self, r: DeliveryRequest) -> DeliveryResult:
        digest = canonical_digest(r)
        if not r.qualification_digest.startswith("sha256:"):
            return DeliveryResult(
                DeliveryState.BLOCKED,
                digest,
                blocker="qualification receipt is not authenticated",
            )
        if any(".." in p or p.startswith("/") for p in r.changed_paths):
            return DeliveryResult(
                DeliveryState.BLOCKED, digest, blocker="invalid changed path"
            )
        if re.search(
            r"(token|secret|password|api[_-]?key)\s*[:=]", r.content_digest, re.I
        ):
            return DeliveryResult(
                DeliveryState.BLOCKED, digest, blocker="secret-bearing content"
            )
        if r.artifact_kind is ArtifactKind.LESSONS_ONLY and any(
            p.endswith((".py", ".js", ".ts", ".go", ".rs")) for p in r.changed_paths
        ):
            return DeliveryResult(
                DeliveryState.BLOCKED, digest, blocker="lessons artifact contains code"
            )
        grant = self.grants.get(r.grant_ref)
        if grant is None:
            return DeliveryResult(
                DeliveryState.LOCAL_ARTIFACT_READY,
                digest,
                blocker="delivery grant unavailable",
            )
        if not isinstance(grant, DeliveryGrant) or not grant.allows(r):
            return DeliveryResult(
                DeliveryState.BLOCKED,
                digest,
                blocker="delivery grant is invalid, revoked, or out of scope",
            )
        if self.transport is None:
            return DeliveryResult(
                DeliveryState.LOCAL_ARTIFACT_READY,
                digest,
                blocker="delivery transport unavailable",
            )
        if r.idempotency_key in self.results:
            prior_digest, prior = self.results[r.idempotency_key]
            if prior_digest != digest:
                return DeliveryResult(
                    DeliveryState.BLOCKED,
                    digest,
                    blocker="idempotency key is bound to another request",
                )
            if prior.state in {DeliveryState.PUSH_PENDING, DeliveryState.PR_PENDING}:
                return self._record(
                    r.idempotency_key,
                    digest,
                    DeliveryResult(
                        DeliveryState.RECONCILIATION_REQUIRED,
                        digest,
                        prior.branch_head,
                        prior.pr_id,
                        "prior remote effect must be observed before retry",
                    ),
                )
            return prior
        try:
            self._record(
                r.idempotency_key,
                digest,
                DeliveryResult(DeliveryState.PUSH_PENDING, digest),
            )
            head = self.transport.push(r.run_branch, r.candidate_commit)
            self._record(
                r.idempotency_key,
                digest,
                DeliveryResult(DeliveryState.PR_PENDING, digest, head),
            )
            pr = self.transport.find_or_create_draft(
                r.run_branch,
                r.base,
                "Hive Mind candidate",
                f"Validation receipt: {r.qualification_digest}",
            )
            result = DeliveryResult(DeliveryState.PUBLISHED, digest, head, str(pr))
            return self._record(r.idempotency_key, digest, result)
        except (TimeoutError, ConnectionError):
            return self._record(
                r.idempotency_key,
                digest,
                DeliveryResult(
                    DeliveryState.RECONCILIATION_REQUIRED,
                    digest,
                    blocker="remote effect uncertain",
                ),
            )
        except PermissionError as e:
            return self._record(
                r.idempotency_key,
                digest,
                DeliveryResult(DeliveryState.BLOCKED, digest, blocker=str(e)),
            )

    def reconcile(self, r: DeliveryRequest) -> DeliveryResult:
        digest = canonical_digest(r)
        prior = self.results.get(r.idempotency_key)
        if prior is None or prior[0] != digest:
            return DeliveryResult(
                DeliveryState.BLOCKED, digest, blocker="no matching delivery intent"
            )
        observer = getattr(self.transport, "observe", None)
        if not callable(observer):
            return DeliveryResult(
                DeliveryState.RECONCILIATION_REQUIRED,
                digest,
                prior[1].branch_head,
                prior[1].pr_id,
                "delivery transport cannot observe uncertain effect",
            )
        observed = observer(r)
        if not isinstance(observed, DeliveryResult) or observed.request_digest != digest:
            return DeliveryResult(
                DeliveryState.RECONCILIATION_REQUIRED,
                digest,
                blocker="remote observation is absent or mismatched",
            )
        return self._record(r.idempotency_key, digest, observed)
