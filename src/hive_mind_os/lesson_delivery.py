"""Durable lessons-only publication obligation and N15 routing (N21)."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from .brain_kernel.canonical import canonical_digest, canonical_document
from .delivery_broker import (
    ArtifactKind,
    DeliveryBroker,
    DeliveryRequest,
    DeliveryResult,
    DeliveryState,
)
from .durable_contracts import ContractStore


class ObligationState(StrEnum):
    REQUIRED = "REQUIRED"
    RETAINED_DRAFT = "RETAINED_DRAFT"
    COMMITTED_DRAFT = "COMMITTED_DRAFT"
    UPSTREAM_PENDING = "UPSTREAM_PENDING"
    DRAFT_PR_OPEN = "DRAFT_PR_OPEN"
    BLOCKED_EXPORT_AUTHORITY = "BLOCKED_EXPORT_AUTHORITY"
    BLOCKED_EXPORT_DESTINATION = "BLOCKED_EXPORT_DESTINATION"
    EXPORT_FAILED_RETRYABLE = "EXPORT_FAILED_RETRYABLE"
    QUARANTINED_EXPORT = "QUARANTINED_EXPORT"


@dataclass(frozen=True, slots=True)
class LessonDeliveryObligation:
    external_mission_id: str
    origin_mission_token: str
    subject_id: str
    safe_draft_digest: str
    local_artifact_path: str
    local_commit_sha: str | None
    upstream_repository_id: str | None
    upstream_path: str | None
    export_authority_digest: str | None
    delivery_idempotency_key: str
    obligation_state: ObligationState = ObligationState.REQUIRED
    upstream_pr_url: str | None = None
    upstream_head_sha: str | None = None
    failure_code: str | None = None

    def __post_init__(self):
        if any(
            type(x) is not str or not x.strip()
            for x in (
                self.external_mission_id,
                self.origin_mission_token,
                self.subject_id,
                self.safe_draft_digest,
                self.local_artifact_path,
                self.delivery_idempotency_key,
            )
        ):
            raise ValueError("delivery identity is required")
        if self.upstream_path and (
            self.upstream_path.startswith("/") or ".." in self.upstream_path.split("/")
        ):
            raise ValueError("invalid upstream path")
        if "/" in self.external_mission_id or "\\" in self.external_mission_id:
            raise ValueError("external mission id cannot contain path separators")

    @property
    def digest(self):
        return canonical_digest(self)

    def to_dict(self):
        return canonical_document(self)

    @classmethod
    def from_dict(cls, value):
        fields = set(cls.__dataclass_fields__)
        if set(value) != fields:
            raise ValueError("closed delivery schema")
        return cls(
            **{**value, "obligation_state": ObligationState(value["obligation_state"])}
        )


class DeliveryLedger:
    def __init__(self):
        self._items = {}

    def admit(self, item):
        key = item.subject_id + ":" + item.external_mission_id
        if (
            key in self._items
            and self._items[key].safe_draft_digest != item.safe_draft_digest
        ):
            raise ValueError("mission obligation already exists")
        self._items.setdefault(key, item)
        return self._items[key]

    def get(self, subject_id, mission_id):
        return self._items.get(subject_id + ":" + mission_id)

    def update(self, item):
        key = item.subject_id + ":" + item.external_mission_id
        old = self._items.get(key)
        if old is None:
            raise ValueError("lesson delivery obligation was not admitted")
        if (
            old.safe_draft_digest != item.safe_draft_digest
            or old.delivery_idempotency_key != item.delivery_idempotency_key
        ):
            raise ValueError("lesson delivery identity cannot change")
        allowed = {
            ObligationState.REQUIRED: {
                ObligationState.RETAINED_DRAFT,
                ObligationState.QUARANTINED_EXPORT,
            },
            ObligationState.RETAINED_DRAFT: {
                ObligationState.COMMITTED_DRAFT,
                ObligationState.BLOCKED_EXPORT_AUTHORITY,
                ObligationState.BLOCKED_EXPORT_DESTINATION,
                ObligationState.UPSTREAM_PENDING,
                ObligationState.QUARANTINED_EXPORT,
            },
            ObligationState.COMMITTED_DRAFT: {
                ObligationState.UPSTREAM_PENDING,
                ObligationState.DRAFT_PR_OPEN,
                ObligationState.BLOCKED_EXPORT_AUTHORITY,
                ObligationState.BLOCKED_EXPORT_DESTINATION,
                ObligationState.EXPORT_FAILED_RETRYABLE,
                ObligationState.QUARANTINED_EXPORT,
            },
            ObligationState.UPSTREAM_PENDING: {
                ObligationState.DRAFT_PR_OPEN,
                ObligationState.BLOCKED_EXPORT_AUTHORITY,
                ObligationState.BLOCKED_EXPORT_DESTINATION,
                ObligationState.EXPORT_FAILED_RETRYABLE,
                ObligationState.QUARANTINED_EXPORT,
            },
            ObligationState.EXPORT_FAILED_RETRYABLE: {
                ObligationState.DRAFT_PR_OPEN,
                ObligationState.BLOCKED_EXPORT_AUTHORITY,
                ObligationState.BLOCKED_EXPORT_DESTINATION,
                ObligationState.QUARANTINED_EXPORT,
            },
            ObligationState.BLOCKED_EXPORT_AUTHORITY: {
                ObligationState.UPSTREAM_PENDING,
                ObligationState.DRAFT_PR_OPEN,
                ObligationState.QUARANTINED_EXPORT,
            },
            ObligationState.BLOCKED_EXPORT_DESTINATION: {
                ObligationState.UPSTREAM_PENDING,
                ObligationState.DRAFT_PR_OPEN,
                ObligationState.QUARANTINED_EXPORT,
            },
            ObligationState.DRAFT_PR_OPEN: set(),
            ObligationState.QUARANTINED_EXPORT: set(),
        }
        if item.obligation_state not in allowed[old.obligation_state]:
            raise ValueError("invalid lesson delivery transition")
        self._items[key] = item
        return item


class DurableDeliveryLedger(DeliveryLedger):
    def __init__(self, path):
        super().__init__()
        self._store = ContractStore(path, LessonDeliveryObligation.from_dict)

    def admit(self, item):
        key = item.subject_id + ":" + item.external_mission_id
        old = self._store.get(key)
        if old and old.safe_draft_digest != item.safe_draft_digest:
            raise ValueError("mission obligation already exists")
        if old is not None:
            self._items[key] = old
            return old
        result = super().admit(item)
        self._store.put(key, result)
        return result

    def get(self, subject_id, mission_id):
        return self._store.get(subject_id + ":" + mission_id) or super().get(
            subject_id, mission_id
        )

    def update(self, item):
        key = item.subject_id + ":" + item.external_mission_id
        old = self.get(item.subject_id, item.external_mission_id)
        if old is not None:
            self._items[key] = old
        result = super().update(item)
        self._store.put(key, result)
        return result


class LessonDeliveryCoordinator:
    """Retain one safe draft and route its optional export through N15."""

    def __init__(self, ledger: DeliveryLedger, broker: DeliveryBroker):
        self.ledger = ledger
        self.broker = broker

    def retain(
        self,
        obligation: LessonDeliveryObligation,
        *,
        target_root: str | Path,
        safe_draft: bytes,
    ) -> LessonDeliveryObligation:
        admitted = self.ledger.admit(obligation)
        expected_path = (
            f".hivemind/lessons/drafts/{obligation.external_mission_id}.md"
        )
        if obligation.local_artifact_path != expected_path:
            raise ValueError("lesson draft path is not the mission-owned draft path")
        digest = "sha256:" + sha256(safe_draft).hexdigest()
        if digest != obligation.safe_draft_digest:
            raise ValueError("safe draft bytes do not match the admitted digest")
        text = safe_draft.decode("utf-8")
        if "document_status: DRAFT" not in text or "processing_state:" not in text:
            raise ValueError("lesson artifact must preserve draft and processing states")
        root = Path(target_root).resolve()
        destination = (root / obligation.local_artifact_path).resolve()
        try:
            destination.relative_to(root)
        except ValueError as exc:
            raise ValueError("lesson draft path escapes its target repository") from exc
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and destination.read_bytes() != safe_draft:
            raise ValueError("retained lesson draft conflicts with admitted bytes")
        if not destination.exists():
            temporary = destination.with_name(f".{destination.name}.{uuid4()}.tmp")
            try:
                with temporary.open("xb") as handle:
                    handle.write(safe_draft)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, destination)
            finally:
                temporary.unlink(missing_ok=True)
        if admitted.obligation_state is not ObligationState.REQUIRED:
            return admitted
        return self.ledger.update(
            replace(admitted, obligation_state=ObligationState.RETAINED_DRAFT)
        )

    def publish(
        self,
        obligation: LessonDeliveryObligation,
        request: DeliveryRequest,
        *,
        reconcile: bool = False,
    ) -> LessonDeliveryObligation:
        current = self.ledger.get(
            obligation.subject_id, obligation.external_mission_id
        )
        if current is None:
            raise ValueError("lesson delivery obligation was not admitted")
        if not current.upstream_repository_id or not current.upstream_path:
            return self.ledger.update(
                replace(
                    current,
                    obligation_state=ObligationState.BLOCKED_EXPORT_DESTINATION,
                    failure_code="export-destination-unavailable",
                )
            )
        if not current.export_authority_digest:
            return self.ledger.update(
                replace(
                    current,
                    obligation_state=ObligationState.BLOCKED_EXPORT_AUTHORITY,
                    failure_code="export-authority-unavailable",
                )
            )
        if (
            request.artifact_kind is not ArtifactKind.LESSONS_ONLY
            or request.target != current.upstream_repository_id
            or request.content_digest != current.safe_draft_digest
            or request.idempotency_key != current.delivery_idempotency_key
            or request.changed_paths != (current.upstream_path,)
        ):
            raise ValueError("delivery request does not match the lesson obligation")
        pending = current
        if current.obligation_state in {
            ObligationState.RETAINED_DRAFT,
            ObligationState.COMMITTED_DRAFT,
            ObligationState.BLOCKED_EXPORT_AUTHORITY,
            ObligationState.BLOCKED_EXPORT_DESTINATION,
        }:
            pending = self.ledger.update(
                replace(
                    current,
                    obligation_state=ObligationState.UPSTREAM_PENDING,
                    failure_code=None,
                )
            )
        result = self.broker.reconcile(request) if reconcile else self.broker.prepare(request)
        return self._record_result(pending, result)

    def _record_result(
        self, obligation: LessonDeliveryObligation, result: DeliveryResult
    ) -> LessonDeliveryObligation:
        if result.state is DeliveryState.PUBLISHED:
            state = ObligationState.DRAFT_PR_OPEN
            failure = None
        elif result.state is DeliveryState.LOCAL_ARTIFACT_READY:
            state = ObligationState.BLOCKED_EXPORT_AUTHORITY
            failure = result.blocker or "export-not-published"
        elif result.state is DeliveryState.BLOCKED:
            state = ObligationState.BLOCKED_EXPORT_AUTHORITY
            failure = result.blocker or "export-blocked"
        else:
            state = ObligationState.EXPORT_FAILED_RETRYABLE
            failure = result.blocker or "export-reconciliation-required"
        return self.ledger.update(
            replace(
                obligation,
                obligation_state=state,
                upstream_pr_url=result.pr_id,
                upstream_head_sha=result.branch_head,
                failure_code=failure,
            )
        )
